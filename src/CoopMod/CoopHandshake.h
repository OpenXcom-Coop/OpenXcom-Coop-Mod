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
#include <string>

namespace OpenXcom
{

class Game;
class Craft;
class Base;
class SavedBattleGame;
class AlienDeployment;

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

// ----- W1-P2: battle_offer mission identity (WAVE1-RUNBOOK.md SS2.W1, ruling
// D-4 = shape (d); WV-D9 / WV-D28 / WV-D42; WR-8/WR-9/WR-10/WR-23/WR-27,
// IR2-10) -----
//
// THE PROBLEM. A thin client never runs BriefingState, so it never learns what
// mission it is in: the two display labels vanilla mints inside BriefingState
// (strTarget "LANDING SITE-0" / strCraftOrBase "CRAFT> SKYRANGER-1",
// BriefingState.cpp:151-188) stay empty on the client, and ctrl-B - which
// scans getBases() for a craft with isInBattlescape() (BattlescapeState.cpp:
// 2841-2854) - finds nothing there either, so its BriefingState would drop into
// the "should never happen" generic branch (BriefingState.cpp:104-108).
//
// THE ORDERING TRAP (SS2.W1, binding). offerBattle() snapshots the blob at
// generation time and the CALLER pushes BriefingState only AFTERWARDS
// (ConfirmLandingState.cpp:369 vs :371). At offer-build time the labels are
// therefore STILL EMPTY, and the operation name is minted later by RNG::seedless
// inside BriefingState. So the host must mint the labels BEFORE it builds the
// offer, and must not re-mint a DIFFERENT operation name afterwards - the
// re-mint divergence is invisible to the hash, because strTarget/strCraftOrBase
// are saveBlob-hash-EXCLUDED (SharedEcon.cpp:3974).
//
// FOUR CALL SITES, ONE HELPER (WV-D42). mintMissionLabels() is called one line
// above EACH of offerBattle()'s four call sites - Menu/NewBattleState.cpp:809,
// Geoscape/ConfirmLandingState.cpp:369, Geoscape/ConfirmCydoniaState.cpp:179,
// Geoscape/GeoscapeState.cpp:629 - never as a one-site fix.

/// HOST: mint the two BriefingState display labels into the live
/// SavedBattleGame and resolve+remember this battle's AlienDeployment type,
/// BEFORE offerBattle() snapshots the blob. Replicates BriefingState.cpp:73-99
/// (deployment resolution, including the craft->getDestination() Ufo fallback)
/// and BriefingState.cpp:151-188's !_infoOnly body (craft ->
/// getDestination()->getName() + STR_CRAFT_; base -> STR_BASE_UC_; then the
/// RNG::seedless operation name when the mod defines operationNames - which
/// covers the BASE path too, IR2-10). RNG::seedless does not touch the synced
/// stream, so this is RNG-neutral. Self-guarding: a no-op unless this machine
/// is the coop host with a live SavedBattleGame, so every SP path through the
/// four call sites stays byte-identical (vanilla BriefingState still mints).
void mintMissionLabels(Game* game, Craft* craft, Base* base);

/// True once this battle's mission identity exists on this machine - minted by
/// mintMissionLabels() on the host, applied from battle_offer.missionLabel on
/// the client. Cleared at the teardown chokepoint (resetPendingState()).
bool missionLabelsCarried();

/// The RESOLVED AlienDeployment TYPE carried by battle_offer.missionLabel
/// (empty when none resolved). Test/introspection accessor - TestServer's
/// battle_state probe reports it (WR-23).
const std::string& carriedDeploymentType();

/// BriefingState hook: the ONE guarded coop call on its deployment-resolution
/// site. Pass whatever vanilla resolved (BriefingState.cpp:73-99) and use the
/// return value.
///  - vanilla resolved something  -> returned UNCHANGED (this is the normal
///    path on the host, and also on a client whose streamed world happens to
///    still contain the in-battlescape Craft).
///  - vanilla resolved nothing and this battle carries a deployment -> the
///    CARRIED one. A machine with no Craft and no Ufo cannot run vanilla's
///    craft->getDestination() fallback, so `deployment` stays null for every
///    mission whose type is not itself a deployment name (the normal case for
///    STR_UFO_CRASH_RECOVERY) and the briefing would render the generic
///    "should never happen" branch (BriefingState.cpp:104-108).
///  - neither -> nullptr, i.e. vanilla's own outcome, unchanged.
/// In a coop battle the outcome is LOGGED (VANILLA / CARRIED / NONE) - that
/// line is how test_rw_mission_labels.py proves the generic fallback was not
/// taken, independently of which of the two resolutions happened to win on the
/// fixture. Silent and inert in SP.
AlienDeployment* resolveBriefingDeployment(Game* game, AlienDeployment* vanillaResolved);

/// BriefingState hook (SS2.W1 RE-MINT SUPPRESSION): true when this machine
/// already minted the mission labels before the offer, so BriefingState's own
/// UNCONDITIONAL `if (!_infoOnly)` label-write body (BriefingState.cpp:151-188)
/// must be a no-op - mintMissionLabels() is a line-for-line replica of it and
/// already ran, and the offer already told the client what it produced.
///
/// WHY THE WHOLE BODY AND NOT JUST THE OPERATION-NAME BLOCK (traced by
/// test_rw_mission_labels.py, 2026-09-02 - the packet text's narrower
/// "operation-name mint" wording does NOT achieve its own stated goal): the
/// body writes strTarget TWICE. The craft branch at :156-160 writes
/// craft->getDestination()->getName() ("LANDING SITE-0"), and the
/// operation-name block at :171-187 then OVERWRITES it with the random name
/// ("Dauntless Rampart") whenever the mod defines operationNames. Guarding only
/// the second half leaves the first half free to clobber the operation name the
/// offer already shipped, so the host ends up on "LANDING SITE-0" while the
/// client shows "Dauntless Rampart" - the exact two-different-mission-names bug
/// D-4 was ruled to fix, merely reached from the other direction. The frozen
/// TRIGGER is unchanged (SS2.W1: "a no-op when battleSave->getMissionTarget()
/// is already non-empty"); only the guarded EXTENT is the whole block.
///
/// False in SP and for any battle with no coop mission identity, so vanilla is
/// byte-identical.
bool missionLabelsAlreadyMinted(const SavedBattleGame* battle);

/// BattlescapeState hook: may ctrl-B open an info-only BriefingState here?
/// True in SP, outside a coop battle, and on the host (which owns the Craft the
/// ctrl-B scan looks for). On a thin client: only once the offer's mission
/// identity has arrived - without it the pushed BriefingState renders the
/// generic fallback with empty labels (SS2.W1's "ctrl-B gated until labels
/// exist").
bool mayReopenBriefing(Game* game);

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

/// R2-P11 (RB-D26): test-only, one-shot corrupt-next-blob lever. HOST: sets a
/// flag offerBattle() checks (and clears) right after it computes blobSha -
/// flips byte 0 of the persisted coopFilesHost["battlehost"] blob AFTER that
/// sha, so the client's post-stream blobSha verify (not offerBattle's own
/// hashing) is what is expected to catch it and refuse {reason:"corrupt"}.
/// Permanent replacement for the R4-P1 packet's temporary OXC_RW_CORRUPT_BLOB
/// env-var lever (removed in that same packet, see its packet report). A
/// request made with no offer in flight, or on a client (there is nothing to
/// corrupt there), is silently consumed by the next offerBattle() call or
/// cleared at teardown (resetPendingState()) - never carries across battles.
void requestCorruptNextBlob();

} // namespace CoopHandshake

} // namespace OpenXcom
