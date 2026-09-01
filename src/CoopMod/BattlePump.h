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
#include <cstddef>
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

/// R2-P11: the highest seq nextSeq() has minted this battle (0 = none yet,
/// same "0 reserved" convention as CoopPump::lastSeqApplied()) - a read-only
/// peek, unlike nextSeq() itself (which mints on every call). event_state's
/// "lastSeqEmitted" field.
std::uint32_t lastSeqEmitted();

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

/// R2-P11: how many battle-lane sends have hit the MN-8 g_txQ-overflow
/// blocking-wait bypass at least once, this battle (event_state's
/// "txDrains" field). 0 in the overwhelmingly common case (a battle-lane
/// message only blocks when the socket thread falls behind).
std::uint32_t txDrainEvents();

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

/**
 * R2-P9 (rewrite spike, SPIKE-RUNBOOK.md SS2.8): the client-side post-apply
 * hash verify. SS2.8's compare direction is one-way in the spike - "host
 * ships h in evs; CLIENT hashes post-apply, compares, hard-fails" (host
 * never compares) - so this is the ONE call site for the whole mismatch
 * path (bucket compare -> freeze -> bt_desync -> bundle -> banner).
 *
 * Body lives in connectionTCP.cpp, next to BattleAuthority/CoopArbiter/
 * CoopPump/CoopEmit/CoopHandshake/CoopBattleUi - the established home for
 * this scaffolding (R2-P1..P9).
 */
namespace CoopHashCheck
{

/// Called from CoopPump::drainApplyQueue() immediately after
/// CoopDisplayQueue::onApplied() for each bt_ev/bt_action_end, in strict seq
/// order. Presence-gated (SS2.8, same as battle_ready.h pre-R2-P9): a no-op
/// if @a evOrEnd carries no non-empty "h" object. Otherwise recomputes every
/// bucket @a evOrEnd names via SharedEcon::computeBattleHashes() against
/// this machine's own live battle and compares hex-for-hex, in the order the
/// carried buckets appear. On the FIRST mismatch: logs, sets
/// BattleAuthority::desyncFrozen (+ g_battleFrozen, halting the apply queue
/// too), sends bt_desync, writes SharedEcon::writeDesyncBundle(), and shows
/// the sticky CoopBattleUi banner - then stops comparing (SS2.8: "NO partial
/// repair"). Latches: a battle that already desynced does not re-report on
/// every later envelope. No-op outside an active coop battle or with no
/// live SavedBattleGame.
void verify(const Json::Value& evOrEnd);

} // namespace CoopHashCheck

/**
 * R2-P11 (SPIKE-RUNBOOK.md RB-D32, DESIGN sec 6 journaling guardrail 6): the
 * flat preallocated event ring TestServer's `event_log` command reads from -
 * "crash-handler-dumpable" by construction (a fixed-size C array of a POD
 * struct, never a std::vector that could be mid-reallocation or a std::string
 * that could be mid-heap-op at crash time). Populated on BOTH machines, but
 * at different call sites per role (there is no wire loopback - the host
 * never receives its own broadcast back): the HOST records at CoopEmit::
 * sendEv() (connectionTCP.cpp), right after seq is stamped - the one choke
 * point every host-side emit (CoopArbiter's kneel/onChainQuiesced's
 * action_end) already goes through; the CLIENT records at CoopPump::
 * drainApplyQueue() (connectionTCP.cpp), right after an envelope clears the
 * strict-seq-order check - so a battle with no desync ends up with matching
 * ring content on both machines despite the different population points.
 * Storage lives in connectionTCP.cpp, next to CoopPump/CoopEmit's own queue
 * globals - this header only declares the API + the Entry shape.
 */
namespace CoopEventLog
{

/// One ring slot. Fixed-size throughout (no heap-backed members) so the ring
/// itself never allocates past its initial static storage.
struct Entry
{
	std::uint32_t seq = 0;
	std::uint32_t actionId = 0;
	/// bt_ev's own "kind" (turn/kneel/...) when present; otherwise the
	/// envelope's "state" (e.g. "bt_action_end", which carries no "kind" of
	/// its own, SS2.3) - always non-empty for anything record() was ever
	/// called with. Fixed-size, truncated if longer (spike kinds are short).
	char kind[24] = { 0 };
	/// Whether this envelope carried a non-empty "h" object (SS2.8/RB-D14) -
	/// event_log's own "h" field is this bool, not the hash values themselves
	/// (use hash_now for actual bucket values).
	bool hasHash = false;
};

/// Ring capacity (preallocated, never resized).
const std::size_t kCapacity = 256;

/// Record one bt_ev / bt_action_end envelope (see this namespace's doc
/// comment above for which role calls this from where). Oldest entry is
/// silently overwritten once the ring is full - "tail" semantics, not a
/// complete-history log.
void record(const Json::Value& evOrEnd);

/// Number of entries currently held (0..kCapacity).
std::size_t size();

/// The entry @a indexFromOldest slots after the oldest one currently held
/// (0 = oldest, size()-1 = newest). Undefined for indexFromOldest >= size()
/// (callers are expected to bound their own loop against size()).
const Entry& at(std::size_t indexFromOldest);

/// Teardown chokepoint: clears the ring back to empty. R2-P8's
/// CoopPump::reset() (this same header) is the established single
/// battle-teardown reset chokepoint; R2-P11 extends its body to call this too.
void reset();

} // namespace CoopEventLog

} // namespace OpenXcom
