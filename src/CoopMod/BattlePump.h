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
#include <cstdint>

#include <json/json.h>

namespace OpenXcom
{

/**
 * R2-P2 (rewrite spike, SPIKE-RUNBOOK.md RB-D5/RB-D14, SS2.2): the battle
 * seq-ordered apply queue (client side) + the seq-mint/emit helpers (host
 * side). This is PLUMBING only - no real appliers yet (R3 fills the
 * "R3-P1 applies payload here" seam in connectionTCP.cpp's
 * CoopPump::drainApplyQueue()). Storage for all of this lives in
 * connectionTCP.cpp, next to the other coop queue globals (g_txQ/g_rxQ/
 * g_rxHold) - this header only declares the API + the freeze flag.
 */

/**
 * The client-side ordered apply queue for bt_ev / bt_action_end (SS2.1's
 * isSeqOrdered() kinds). RB-D5: drainApplyQueue() is called from
 * connectionTCP::updateCoopTask() - the existing main-thread pump point,
 * which already runs even when modal states sit on top of BattlescapeState.
 * Appliers set flags only - drainApplyQueue() must never push/pop a State
 * or touch a BState.
 */
namespace CoopPump
{

/// Enqueue one bt_ev / bt_action_end envelope (already parsed JSON) for
/// in-order apply. Thread-safe (mutex-guarded) even though, as of R2-P2,
/// every real call site is already on the main/pump thread (the battle-lane
/// RX branch in onTCPMessage, itself only ever reached from
/// updateCoopTask()'s g_rxHold consume loop) - kept thread-safe defensively
/// per the frozen R2-P2 contract, in case a future packet feeds it directly
/// from a socket thread.
void enqueue(const Json::Value& evOrEnd);

/// Drain the queue in strict seq order (SS2.2: one monotonic stream,
/// battle-wide, across all origins). Called from updateCoopTask() (RB-D5),
/// gated on a live SavedBattleGame (the R2-P3 BattleAuthority phase gate
/// will tighten this later - see the "// R2-P3 phase gate" marker at the
/// call site). A GAP (next seq != lastSeqApplied()+1) is a protocol bug:
/// logs the gap and sets g_battleFrozen, then stops draining (the
/// out-of-order entry is left queued, not discarded, in case a later
/// packet's desync report wants it). Never calls pushState/popState or any
/// BState op - appliers set flags only (RB-D5).
void drainApplyQueue();

/// Highest seq successfully applied this battle (0 = none yet, SS2.2).
std::uint32_t lastSeqApplied();

/// Number of envelopes currently queued (applied + gap-blocked entries not
/// yet consumed).
std::uint32_t queueDepth();

/// Teardown chokepoint: clears the queue, lastSeqApplied, the freeze flag,
/// and (SS2.2 "reset by a new battle") CoopEmit's host seq-mint counter.
/// R2-P8 wires the actual call site at the battle teardown chokepoint; this
/// packet only implements the function.
void reset();

} // namespace CoopPump

/**
 * Host-side seq mint + battle-lane emit helpers. Every message shipped
 * through CoopEmit is, by construction, a battle-lane kind (SS2.1) - so
 * every one of them gets the MN-8 TX-drain bypass (connectionTCP.cpp): on
 * g_txQ overflow the emitter blocks (bounded wait + watchdog log) instead
 * of dropping, unlike the default enqueueTx() drop-newest behavior. Socket
 * writes still happen only on the socket threads (their existing g_txQ.pop
 * + sendAll loops) - CoopEmit never calls sendAll itself (REVIEW3 F3).
 */
namespace CoopEmit
{

/// Host mint: uint32, starts at 1 per battle, monotonic, never reused
/// within a battle (SS2.2). Main/pump-thread only (host-side emit sites are
/// all reached from the main thread in this codebase, RB-D5).
std::uint32_t nextSeq();

/// Ships @a msg as-is (stamps nothing) - for the non-seq battle-lane kinds
/// (bt_ack/bt_deny/bt_intent/the handshake set). The caller has already set
/// every field (iseq/seat/reason/etc.) via CoopWire's makers.
void sendBattle(Json::Value& msg);

/// Stamps ev["seq"] = nextSeq() (overwriting whatever placeholder the
/// caller passed, e.g. from CoopWire::makeEv(0, ...)) and ships it. Works
/// mechanically for both bt_ev and bt_action_end (both carry a top-level
/// "seq" field per SS2.3) - R2-P2 defines only this one sender; a later
/// packet decides whether action_end reuses it or gets its own thin
/// wrapper.
void sendEv(Json::Value ev);

} // namespace CoopEmit

/**
 * IR-16c: the S3 display-decouple hook. Declared here so
 * CoopPump::drainApplyQueue() has something to call once an envelope is
 * verified in-order; the body is a no-op until R3-P1 fills it in. Must stay
 * cheap and side-effect-free at the BState/State level for the same reason
 * drainApplyQueue() itself must (RB-D5).
 */
namespace CoopDisplayQueue
{

void onApplied(const Json::Value& ev);

} // namespace CoopDisplayQueue

/// R2-P2: set (by CoopPump::drainApplyQueue()) the moment a seq gap is
/// detected on the client apply queue - a protocol bug, never expected in
/// normal play (a single ordered TCP stream should never reorder). Battle
/// input should be treated as frozen for as long as this is true. R2-P9's
/// desync REPORT/bundle plumbing and BattleAuthority (R2-P3+) are the
/// intended readers/clearers of this flag; R2-P2 only sets it and logs.
extern std::atomic<bool> g_battleFrozen;

} // namespace OpenXcom
