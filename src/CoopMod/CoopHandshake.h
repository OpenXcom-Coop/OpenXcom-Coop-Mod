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

#include <json/json.h>

namespace OpenXcom
{

class Game;

/**
 * R4-P1 (rewrite spike, SPIKE-RUNBOOK.md SS2.7, RB-D18, IR-5, IR-6): the
 * battle-start handshake - host offer -> client accept -> blob stream ->
 * client load -> ready -> hash-equal -> phase Active on BOTH machines.
 *
 * HOST sequence: offerBattle() is called once vanilla BattlescapeGenerator::
 * run() has produced the live battle save (classic/SHARED skirmish or
 * campaign mission-confirm entry, RB-D18's interim scope) - the SAME point
 * the vanilla SP path pushes BriefingState. It mints a battleId, snapshots
 * the battle via the existing SavedGame::saveCoopToMemory("battlehost", ...)
 * call shape, sha256s the blob (libsodium crypto_hash_sha256, IR-6 - never
 * hand-rolled), and sends battle_offer.
 *
 * IMPORTANT (first-attempt finding, kept here so it is not re-discovered):
 * offerBattle() touches ONLY BattleAuthority/CoopEmit/the coop file maps - it
 * deliberately does NOT touch the caller's state stack. The caller (NewBattle
 * State::btnOkClick / ConfirmLandingState::btnYesClick) still pushes
 * BriefingState immediately afterward, exactly like vanilla SP - an earlier
 * version of this packet tried to DEFER that push until battle_ready
 * succeeded (so a refused/corrupt handshake could never leave the host
 * "inside" a coop battle), but Game::popState() removes the popped state from
 * Game::_states IMMEDIATELY (only the C++ delete is deferred to the next
 * cycle, per Game::popState()'s own doc comment) - so the caller's existing
 * two popState() calls left the ENTIRE state stack empty for the one frame
 * between offerBattle() returning and the (then-missing) BriefingState push,
 * and Game::run() crashed (SIGABRT/exit code 3, no WER dump - a C++
 * exception, not an AV) on the very next cycle. Never leave Game::_states
 * empty across a return from a State's own click handler. The fix: push
 * BriefingState unconditionally and immediately (byte-identical to vanilla,
 * zero SP-path behavior change) and instead make the FAILURE paths
 * (onRefuse()/onReady() mismatch) unwind the host's UI with a bounded
 * pop-to-safe-state loop (see connectionTCP.cpp's coopUnwindToSafeState()) -
 * the same "keep this bounded, never assume a specific stack depth" pattern
 * connectionTCP.cpp's own close_load_progress handler already uses
 * (its "inBattleResume" guarded while loop).
 *
 * On battle_accept the blob streams over the KEPT sendMissionFile carrier
 * (map_result_data 3KB chunks + WAIT_MAP_SENDER ack). On battle_ready it
 * compares the saveBlob bucket (IR-5's interim, presence-gated compare -
 * R2-P9 upgrades this to the full SS2.8 sweep): a match flips phase to
 * Active (the host's own BriefingState/BattlescapeState navigation is
 * whatever vanilla input already did with it - unaffected either way, RB-D10
 * "the host plays vanilla directly"); a mismatch tears down AND unwinds.
 *
 * CLIENT sequence (the onOffer/finishLoad handlers below, called from the
 * connectionTCP.cpp battle-lane handshake dispatch this packet adds): verify
 * protocolVersion/phase/gamemode (refuse version|busy|unsupported), accept;
 * receive chunks via the EXISTING generic "map_result_data" handler
 * (unmodified - this packet only adds a byte-count completion check next to
 * it, see the "R4-P1: blob transfer complete" marker in connectionTCP.cpp);
 * once accumulated bytes reach the offered blobBytes, verify blobSha
 * (libsodium) BEFORE loading - a mismatch refuses {reason:"corrupt"} and
 * returns cleanly (nothing was ever loaded, so there is nothing to unwind);
 * on a match, load into a fresh SavedGame (the SavedGame::
 * loadCoopSaveFromMemory precedent at connectionTCP.cpp's writeHostMapFile()),
 * rebuild CoopIdMaps, stamp authority {hostSim:false, localSeat, phase:Active},
 * compute its own saveBlob bucket, push BattlescapeState directly (the
 * LoadGameState.cpp "loaded save with a live battle -> BattlescapeState"
 * precedent - no client-side BriefingState, this machine did not generate the
 * mission; the client's own state stack is never left empty either, since
 * this only ever ADDS a state, never pops one), and answer with battle_ready.
 *
 * Bodies live in connectionTCP.cpp, next to BattleAuthority/CoopArbiter/
 * CoopIdMaps/CoopPump/CoopEmit - the established home for this scaffolding
 * (R2-P1..P8). All four handshake sends go through CoopEmit::sendBattle()
 * (matching CoopArbiter's own deny()/ack() sends) so they get the MN-8
 * TX-drain bypass battle-lane messages are entitled to.
 */
namespace CoopHandshake
{

/// HOST: call once vanilla BattlescapeGenerator::run() has produced the live
/// battle save (@a game->getSavedGame()->getSavedBattle() is non-null) - the
/// SAME point the vanilla SP path pushes BriefingState; the caller still owns
/// that push (see this header's top doc comment for why). @a gamemode is
/// connectionTCP::_coopGamemode (RB-D23's gamemode source). No-op (logs) if
/// this machine is not the coop host, if there is no live SavedBattleGame
/// yet, or if a handshake/battle is already in flight (phase != Idle) - the
/// last case is a local double-offer guard, not the wire "busy" refuse
/// (SS2.1: battle_refuse is client->host only; a receiving CLIENT is what
/// evaluates and sends "busy").
void offerBattle(Game* game, int gamemode);

// ----- client-inbound handlers (battle_offer, and the blob-complete check
// wired into the existing generic map_result_data handler) -----

/// CLIENT: battle_offer received. Verifies protocolVersion/phase/gamemode
/// (SS2.1/RB-D18) and answers battle_accept or battle_refuse.
void onOffer(Game* game, const Json::Value& offer);

/// CLIENT: called after EVERY "map_result_data" chunk append (the existing,
/// unmodified generic carrier handler) - a no-op unless a battle-blob
/// transfer is currently in flight (onOffer() armed it after accepting).
/// Once the accumulated bytes reach the offered blobBytes, verifies blobSha
/// and either loads the battle (-> battle_ready) or refuses {reason:
/// "corrupt"} and cleans up (-> back to Idle, nothing was loaded).
void onBlobChunkAppended(Game* game);

// ----- host-inbound handlers -----

/// HOST: battle_accept received. Starts the blob stream via the surviving
/// map_result_data/WAIT_MAP_SENDER carrier.
void onAccept(Game* game, const Json::Value& accept);

/// HOST: battle_refuse received (any reason). Tears the handshake down
/// (resetBattleAuthority(), drop the generated battle) and logs the reason,
/// then unwinds the host's UI back to a safe state (see this header's top
/// doc comment) - the host's own BriefingState/BattlescapeState navigation
/// is unaffected by the handshake's progress, so it may already be sitting
/// past Briefing by the time a refusal arrives.
void onRefuse(Game* game, const Json::Value& refuse);

/// HOST: battle_ready received. Compares the client's saveBlob bucket
/// against the host's own (computed once in offerBattle(), IR-5's interim
/// presence-gated compare). On a match: phase -> Active. On a mismatch:
/// logs, tears down and unwinds exactly like onRefuse().
void onReady(Game* game, const Json::Value& ready);

/// Teardown chokepoint (R2-P8's clearNetworkSessionQueues() family, #82
/// GoToMainMenuState invariant): clears every R4-P1 pending-handshake static
/// this header's functions maintain (the client's in-flight blob-expectation
/// state, the host's pending saveBlob-hash state) so a mid-handshake
/// disconnect cannot leak into the next session.
void resetPendingState();

} // namespace CoopHandshake

} // namespace OpenXcom
