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

class SavedBattleGame;
class BattleUnit;
class BattleItem;
class Tile;
class Position;
class Projectile;
struct BattleAction;
struct BattleActionAttack;
struct RuleDamageType;

/**
 * W2-P2 (rewrite wave 2, docs rewrite/prompts/w2p2_delta_core.md, owner ruling
 * D128 = (b)): the DELTA CORE. Every host event carries a `delta` - the
 * absolute value of every synced field that changed since the previous event -
 * attached at the one host emit choke (CoopEmit::sendEv), and the client writes
 * those values with plain setters, never by re-running the simulation.
 *
 * Stage S-A: commit S-A.1 (the RED commit, spec (d)) declared the spec (b)16
 * probes' read accessors and the `delta_drop_next` lever's one-shot request;
 * commit S-A.2 adds the snapshot, diff, attach, seed, reset, absorb and `sync`
 * flush below (the client applier is CoopApply::applyDelta, inside
 * connectionTCP.cpp's CoopApply region). The storage lives in connectionTCP.cpp
 * just above `namespace CoopEmit` (spec (b)3), next to the other battle-scoped
 * coop globals; the counters are reset by resetBattleAuthority() (spec (b)5).
 *
 * Every probe is TEST INTROSPECTION ONLY (TestServer `event_state`), battle-
 * scoped, and never read by game logic. Timings are local measurements, never
 * put on the wire (G1).
 */
namespace CoopDelta
{

/// One machine's view of the spec (b)16 delta probes (`event_state` fields in
/// brackets). "host" / "client" name the machine that writes the field; the
/// other machine reports its own (normally zero) value.
struct Probes
{
	bool armed = false;      ///< [deltaArmed] the host snapshot is seeded and armed
	int seeds = 0;           ///< [deltaSeeds] CoopDelta seeds this battle (fresh / rejoin / resume)
	int evsEmitted = 0;      ///< [deltaEvsEmitted] host: envelopes that carried a non-empty delta
	int evsApplied = 0;      ///< [deltaEvsApplied] client: envelopes whose delta was applied
	int fieldsApplied = 0;   ///< [deltaFieldsApplied] client: individual field writes applied
	int unresolved = 0;      ///< [deltaUnresolved] an id or tile index that did not resolve
	int addExisting = 0;     ///< [deltaAddExisting] an itemsAdded id that already existed
	int removeMissing = 0;   ///< [deltaRemoveMissing] an itemsRemoved id that did not exist
	int unsupported = 0;     ///< [deltaUnsupported] a change W2-P2 does not carry (logged)
	int absorbed = 0;        ///< [deltaAbsorbed] host: test-lever writes absorbed into the snapshot
	int dropped = 0;         ///< [deltaDropped] host: deltas withheld by `delta_drop_next`
	int diffUsLast = 0;      ///< [deltaDiffUsLast] host: last diff+attach, microseconds
	int diffUsMax = 0;       ///< [deltaDiffUsMax]
	int bytesLast = 0;       ///< [deltaBytesLast] host: last attached delta, serialized bytes
	int bytesMax = 0;        ///< [deltaBytesMax]
	int hashUsLast = 0;      ///< [hashUsLast] host: last emission's `h` build, microseconds
	int hashUsMax = 0;       ///< [hashUsMax]
	int applyUsLast = 0;     ///< [deltaApplyUsLast] client: last applyDelta, microseconds
	int applyUsMax = 0;      ///< [deltaApplyUsMax]
	int syncEvsEmitted = 0;  ///< [syncEvsEmitted] host: `sync` evs emitted
	int syncEvsApplied = 0;  ///< [syncEvsApplied] client: `sync` evs applied
	// W2-P2 S-L (amendment A4.5, owner ruling M6): the client's light
	// recomputes made by CoopApply::applyDelta. Commit S-L.1 (the RED commit)
	// counts today's one whole-map pass; commit S-L.2's vanilla-shaped local
	// calls are the `lightLocalCalls` writers.
	int lightLocalCalls = 0; ///< [lightLocalCalls] client: region (non-whole-map) light recomputes
	int lightWholeCalls = 0; ///< [lightWholeCalls] client: whole-map light recomputes
	int lightUsMax = 0;      ///< [lightUsMax] client: the slowest single light recompute, microseconds
	// W2-P2 S-C (spec (b)13/(b)16): the host's own combat actions. Commit
	// S-C.1 (the RED commit) adds the storage only; commit S-C.2's
	// CoopArbiter::beginHostLocalCombat is the writer.
	int hostCombatContexts = 0; ///< [hostCombatContexts] host: host-local combat contexts begun
	// W2-P2 S-C (amendment A3, F690): the arming guard's deferrals - an
	// onChainQuiesced() that fired INSIDE an armed push pair (the battle_fire
	// lever's turn-then-shot pushes) and was deferred instead of closing the
	// context before the shot state existed.
	int armingDeferrals = 0;    ///< [armingDeferrals] host: quiescences deferred while arming
	// W2-P3 S-A (spec rewrite/prompts/w2p3_nonplayer_origins.md (b)13,
	// amendment B1 RQ5): the action-context counters. Commit S-A.1 (the RED
	// commit) adds the storage only; commit S-A.2 is the writer.
	int contextsClosedAtEndTurn = 0; ///< [contextsClosedAtEndTurn] host: contexts (origin != endturn) closed at endTurn() entry; diagnostic (RQ5)
	int contextBeginRefused = 0;     ///< [contextBeginRefused] host: base context begins refused because a context was open
	// W2-P2 S-H (amendment A5.5, owner ruling D138): the `saveBlob` timings,
	// kept apart from hashUsLast/Max (N19). Commit S-H.1 (the RED commit)
	// times the host's existing saveBlob computations (side_transition, and a
	// structured `h` built with saveBlob); the client's verify arm, and so its
	// timing writer, is commit S-H.2's.
	int saveBlobUsLast = 0;       ///< [saveBlobUsLast] host: last saveBlob computation, microseconds
	int saveBlobUsMax = 0;        ///< [saveBlobUsMax]
	int saveBlobVerifyUsLast = 0; ///< [saveBlobVerifyUsLast] client: last saveBlob verify, microseconds
	int saveBlobVerifyUsMax = 0;  ///< [saveBlobVerifyUsMax]
};

/// A snapshot of this machine's probes (thread-safe; reads atomics).
Probes probes();

/// [lastDelta] the class counts of the last delta this machine emitted
/// (host: the last NON-EMPTY one) or applied (client), as
/// {seq, kind, units, unitsAdded, tiles, nodes, items, itemsAdded,
/// itemsRemoved, battle:[keys]} - or null when there has been none this
/// battle. (`unitsAdded`: W2-P3 S-C.1, spec (b)10/(b)13.)
Json::Value lastDelta();

/// [deltaRing] (W2-P3 S-C.1, amendment B1 RQ7) HOST: the last 32 deltas this
/// machine attached, oldest first, each the lastDelta() record of that
/// envelope plus the ids its classes added or removed - {seq, kind, units,
/// unitsAdded, tiles, nodes, items, itemsAdded, itemsRemoved, battle:[keys],
/// unitsAddedIds:[..], itemsAddedIds:[..], itemsRemovedIds:[..]} - so a test
/// reads the delta of one specific ev by its seq. An empty array on a client
/// and before the first attach. Probe only.
Json::Value deltaRing();

/// [lastLight] (W2-P2 S-L, A4.5) the last light recompute the client's delta
/// applier made, as {seq, kind, layer, x, y, z, radius, terrain, whole, us}
/// (x/y/z = -1 and whole = true for a whole-map pass) - or null when there
/// has been none this battle.
Json::Value lastLight();

/// `light_probe_reset` (W2-P2 S-L, A4.5; test lever): zero this machine's
/// `lightUsMax` and `deltaApplyUsMax` windows. Nothing else changes.
void resetLightWindow();

/// [cueCounts] (W2-P2 S-C, spec (b)11/(b)16) the cue evs of this battle per
/// kind - host: emitted, client: applied - as {kind: count} (an empty object
/// when there has been none). Commit S-C.1 (the RED commit) adds the storage
/// and this reader only; commit S-C.2's cue hooks (host) and cue-kind branch
/// (client) are the writers.
Json::Value cueCounts();

/// [lastCue] (W2-P2 S-C, spec (b)16) the last cue ev this machine emitted
/// (host) or applied (client), as {kind, seq, actionId, payload} - or null
/// when there has been none this battle. Same writers as cueCounts().
Json::Value lastCue();

/// [contextsOpened] (W2-P3 S-A, spec (b)13) host: the action contexts pushed
/// this battle per origin, every origin including wave 1's ("intent", "host",
/// "ai", "endturn", ...), as {origin: count} (an empty object when there has
/// been none). Commit S-A.1 (the RED commit) adds the storage and this reader
/// only; commit S-A.2's context begin paths are the writers.
Json::Value contextsOpened();

/// [closedContexts] (W2-P3 S-A, spec (b)13, amendment B1 RQ7) host: the last
/// 32 action contexts closed this battle, oldest first, as [{actionId, origin,
/// kind, actorId (-1 = actor-less), nestedIn (the base entry's id, 0 for a
/// base context), endSeq (the seq of its bt_action_end, 0 when none was
/// emitted), hasFinal (that bt_action_end carried `final`)}] (an empty array
/// when there has been none). Commit S-A.1 (the RED commit) adds the storage
/// and this reader only; commit S-A.2's context close paths are the writers.
Json::Value closedContexts();

/// [hashVerifyCounts] (W2-P2 S-H, amendment A5.5) client: per bucket name,
/// how many times CoopHashCheck::verify() compared that bucket this battle,
/// equal or not, as {bucket: n} (an empty object when there has been none).
/// A carried bucket verify() does not know (logged and ignored) is not
/// compared, so it is not counted.
Json::Value hashVerifyCounts();

/// [lastHashVerify] (W2-P2 S-H, A5.5) client: the last verify() call that
/// reached its compare loop, as {seq, kind, buckets:[the names it compared,
/// in order]} (`kind` = the ev's kind, else the envelope's state) - or null
/// when there has been none this battle.
Json::Value lastHashVerify();

/// CoopHashCheck::verify()'s two probe hooks (A5.5; probe only, never read by
/// game logic): noteHashVerifyBegin() once, right before the compare loop;
/// noteHashVerifyBucket() once per bucket the loop compares.
void noteHashVerifyBegin(const Json::Value& evOrEnd);
void noteHashVerifyBucket(const std::string& bucket);

/// HOST, RB-D26 one-shot (the `reveal_drop` pattern): the NEXT delta attach
/// computes and commits its delta but does not attach it (bumping `dropped`),
/// so the client is permanently missing those values - a hash-visible
/// divergence that proves the delta, and nothing else, closed the hole.
/// Cleared at battle teardown. Consumed by the next attach() whose delta is
/// non-empty (the reveal_drop pattern) or, when @a cls names a delta class
/// (a spec (b)1 top-level key, e.g. "tiles"; F515), by the next attach()
/// whose delta carries at least one entry of that class.
void requestDropNext(const std::string& cls = std::string());

// ----- W2-P2 S-A, commit S-A.2: the delta core (spec (b)1-6, 9, 15) -----
// Stage S-A syncs UNITS, TILES, NODES and BATTLE COUNTERS (itemIdCtr
// included); items are stage S-B. Bodies: connectionTCP.cpp, just above
// namespace CoopEmit.

/// HOST (spec (b)4): snapshot := live state of @a battle, and arm. Called on
/// the line after each of the three saveCoopToMemory("battlehost") snapshots
/// (fresh offer, rejoin, disk resume) - the exact state the client's blob
/// freezes. Unconditional: phase is still Handshake at the fresh offer.
void seed(SavedBattleGame* battle);

/// Spec (b)5: disarm and clear the snapshot. Called from CoopPump::reset().
/// A disarmed host attaches nothing.
void reset();

/// HOST (spec (b)3), at the CoopEmit::sendEv choke, for the OUTERMOST call
/// only: diff the live state against the snapshot, write env["delta"] when
/// non-empty, and commit the new values. No-op unless armed. Returns true iff
/// a delta was attached.
bool attach(SavedBattleGame* battle, Json::Value& env);

/// HOST (spec (b)9): called from onChainQuiesced()'s empty-context branch.
/// When armed and the delta is non-empty, emits one
/// bt_ev{kind:"sync", actionId:0, payload:{}} carrying it, with h = the 7
/// structured buckets. Self-guarded (coop battle, host sim).
/// W2-P8b S-A.2 (docs rewrite/prompts/w2p8b_prebattle_equip.md, AMENDMENT P8b-1 section 4 steps 4-6, Q2 (a)):
/// with @a equip the `sync` is FORCED - it goes out with an empty delta too - and carries @a equip as its
/// payload's `equip` object (the pre-battle equip phase's open / ready / end signal). Still never inside an open
/// action context; the caller checks CoopEmit::lastSeqEmitted() to learn whether it went out.
void flushSync(const Json::Value* equip = nullptr);

/// W2-P8 S-C1.2 (Q7 (a); AMENDMENT P8-3a Q1 (a)): HOST, co-op battle only - the host's own in-battle
/// inventory change at @a site ("move", "load", "unload", "reload", "close") latches one `sync`. A no-op
/// in single player and on the client. Writes the invHostDirty probe's `pending` and `sets`.
void noteHostInventoryChange(const char* site);

/// W2-P8 S-C1.2 (Q7 (a), F2329): HOST, once per pump pass (updateCoopTask, after the reveal flush) - the
/// latch's consumer: kept while the battle is not quiescent (`heldByGate`), else cleared and flushSync()
/// runs (`flushes` when it sent a `sync`, `emptyFlushes` when the delta was empty).
void flushHostInventoryLatch();

/// HOST, armed only (spec (b)15): a TEST LEVER wrote this object directly;
/// copy its live values into the snapshot so the write never rides a delta
/// (a one-machine poke keeps proving detection; a both-machine write stays
/// equal without a mint race). Bumps `absorbed`. Never called by product code.
void absorbUnit(const BattleUnit* unit);
void absorbTile(const Tile* tile);
void absorbBattle(SavedBattleGame* battle);

// ----- W2-P2 S-B, commit S-B.2: the item delta (spec (b)1, 7, 8, 15) -----
// attach() now also diffs ITEMS: `items` (field changes, incl. ammo links -
// a slot whose ammo is the weapon itself (BattleItem.cpp's `_ammoItem[slot] =
// this`, F530) is encoded as the item's OWN id and restored as self),
// `itemsAdded` (the host's BattleItem::save() YAML, materialized on the client
// with the host's id through the load path) and `itemsRemoved`.

/// HOST, armed only (spec (b)15): a TEST LEVER created or wrote @a item;
/// copy its live values into the snapshot (a new id is added), so the write
/// never rides a delta. Bumps `absorbed`. Never called by product code.
void absorbItem(const BattleItem* item);
/// HOST, armed only (spec (b)15): a TEST LEVER removed item @a id (and each
/// of its ammo ids, one call each); drop it from the snapshot so the removal
/// never rides a delta. Bumps `absorbed`. Never called by product code.
void absorbItemRemoved(int id);

// ----- W2-P7 S-A.1 (the RED commit): the `battleEnd` record -----
// Spec rewrite/prompts/w2p7_battle_end.md, AMENDMENT P7-1 ST4 (a) (F1895,
// F1909, F1910). TEST INTROSPECTION ONLY (TestServer `event_state.battleEnd`),
// never read by game logic, never on the wire. SESSION-LIFETIME: cleared only
// by initBattleAuthority() (battleEndRecordReset), never by
// resetBattleAuthority() or CoopPump::reset(), so a skirmish end's disconnect
// resets on both machines leave it readable. Mutex-guarded (those resets and
// the record can meet on the UDP-monitor thread). Bodies: connectionTCP.cpp,
// in the CoopDelta probe storage block. Commit S-A.1 adds the storage, the
// reader, the zeros, the sendEv evsAfter probe, the drain-depth counter and
// the teardown snapshot; commit S-A.2's host hook, client applier and pump
// consumer are the other writers (battleEndRecordSet / battleEndNoteTeardown).

/// [battleEnd] this machine's record, every key present (zeros before any
/// write): {emitted, applied, seq, reason, aborted, inExitArea,
/// perSeatVerdict:[{seat, verdict}], tally:{liveAliens, liveSoldiers, inExit},
/// actionIdAtEmit, quiescentAtEmit, hBuckets:[], evsAfter, stageSkips,
/// skirmish, latchedMs, tornDownMs, teardownInDrain, quiescentAtTeardown,
/// desyncAtTeardown, bstatePushesAtTeardown, queueDepthAtTeardown,
/// lastSeqApplied, hashVerify (null, or {seq, kind, buckets:[]})}.
Json::Value battleEndRecord();

/// Write key @a key of this machine's record (S-A.2's writers). Probe only.
void battleEndRecordSet(const char* key, const Json::Value& value);

/// Clear this machine's record to its zeros (and the evsAfter arm). Called
/// by initBattleAuthority() only.
void battleEndRecordReset();

/// HOST, CoopEmit::sendEv() right after the seq stamp: the first envelope
/// whose kind is `battle_end` records its stamped seq (`seq`); every envelope
/// stamped after it (a trailing nested reveal included) bumps `evsAfter`.
void battleEndNoteSend(const Json::Value& ev);

/// CLIENT, S-A.2's pump consumer, before its teardown: the teardown snapshots
/// - tornDownMs (SDL_GetTicks), teardownInDrain (CoopPump::drainApplyQueue()'s
/// depth > 0), quiescentAtTeardown (coopBattleQuiescent()), desyncAtTeardown,
/// bstatePushesAtTeardown (coopClientBStatePushes()), queueDepthAtTeardown,
/// lastSeqApplied and hashVerify (lastHashVerify()).
void battleEndNoteTeardown();

/// TEST INTROSPECTION + S-B1.2's finish (AMENDMENT P7-2 R2): true iff @a state is the display-only DebriefingState (identity compare, never dereferenced).
bool debriefIsDisplayOnly(const void* state);

/// W2-P7 S-C-A.2 (AMENDMENT P7-6 PR-2): true while this machine's battle-end debriefing is a campaign one (set at the
/// host's V5 mark / the client's fill of a non-skirmish payload; cleared at the campaign OK and by
/// battleEndRecordReset()).
bool debriefIsCampaign();

// ----- W2-P8 S-C1.1 (the RED commit): the in-battle inventory's S-C1 probes -----
// Spec docs rewrite/prompts/w2p8_inventory.md, S-C1 PINNED STAGE TEXT; AMENDMENT
// P8-3a Q2 (a), Q3 (a). TEST INTROSPECTION ONLY (TestServer event_state), never
// read by game logic, never on the wire. Bodies: connectionTCP.cpp. Commit
// S-C1.1 adds the storage, the zeros, the readers and the resets; commit
// S-C1.2's host latch, its pump consumer and the client force-close write
// them. The record above also gains `inventoryOpenAtTeardown` (CLIENT: an
// InventoryState was on this machine's state stack at battleEndNoteTeardown()).

/// [invHostDirty] HOST: the host's own-inventory `sync` latch - {pending,
/// sets {move, load, unload, reload, close}, flushes (consumer passes that
/// emitted a `sync`), emptyFlushes (passes whose delta was empty), heldByGate
/// (passes that kept the latch because the battle was not quiescent)}.
Json::Value hostInventoryLatchProbe();

/// [invForcedCloses] CLIENT: the inventory force-close - {count, byReason
/// {unit_out, not_commanded, side, battle_end}, notOnTop, coveredDetach (W2-P8
/// S-C2, AMENDMENT P8-4 C2-3: a covered screen's unit detached)}.
Json::Value inventoryForceCloseProbe();

/// Clear the two probes above to their zeros. Called by initBattleAuthority()
/// only, beside battleEndRecordReset() (P8-3a Q2 (a)): the client's battle_end
/// teardown runs resetBattleAuthority() before a test can read them.
void inventoryProbesReset();

/// [invWarningWrites] BOTH: the texts the co-op layer put on the inventory's
/// own message line (every coopInvNoteWarning(); P8-3a Q3 (a), F2604).
/// Battle-scoped with the S-A inventory probes (resetBattleAuthority()).
int invWarningWrites();

// ----- W2-P8 S-C2.1 (the RED commit): the host screen probes -----
// Spec docs rewrite/prompts/w2p8_inventory.md, AMENDMENT P8-4 section 4.2 and
// C2-5 (owner D166 = B, D187-D191). TEST INTROSPECTION ONLY (TestServer
// event_state), never read by game logic, never on the wire. Bodies:
// connectionTCP.cpp. Zeroed and reset by inventoryProbesReset() above (C2-5,
// never by resetBattleAuthority()). Commit S-C2.1 adds the storage, the zeros,
// the readers and the reset; commit S-C2.2's covered-battle driver, host screen
// check, medi-kit recheck and covered detach write them.

/// [hostCovered] HOST: the covered-battle driver - {steps, byOrigin {intent,
/// endturn}, lastTop (the covering top state's class at the last step)}.
Json::Value hostCoveredProbe();

/// [hostScreens] HOST: the host screen check - {closes {count, byReason
/// {unit_out, not_commanded, side}, byScreen {inventory, action_menu, prime,
/// skill, medikit}}, cursorReturned, refreshes, medikitRefused, coveredDetach}.
Json::Value hostScreensProbe();

// ----- W2-P8b S-A.1 (the RED commit): the pre-battle equip phase's probes -----
// Spec docs rewrite/prompts/w2p8b_prebattle_equip.md, AMENDMENT P8b-1 section 4
// ("Shared state", step 10). TEST INTROSPECTION ONLY (TestServer event_state /
// inventory_view), never on the wire. Bodies: connectionTCP.cpp, beside the
// state (g_equip) and its zeros. Commit S-A.1 adds the readers; commit S-A.2's
// equip entry, ready toggle, barrier and end write the state.

/// [equip] BOTH: {phase none|open|ended, hostOpen, openAnnounced, ready [4 bools
/// by seat], counted [4 bools], pile [x,y,z] or null, entryDone, screen (a
/// pre-battle screen is recorded), passThrough, abortPending, barrierDone,
/// okPressed, and the counters entries, closes, heldUntilOpen, lateDenied,
/// endTurnIgnored, readySyncs, endSyncs, waitLineShows, forceCloseSkips,
/// heldTurnScreenPresses} (each field's meaning: connectionTCP.cpp, g_equip).
Json::Value equipProbe();

/// true iff @a state is the pre-battle InventoryState the equip phase recorded
/// (identity compare, never dereferenced) - inventory_view `preBattle`.
bool equipIsScreen(const void* state);

/// The flag the co-op layer last applied to the pre-battle OK button's look
/// (Q8) - inventory_view `okPressed`.
bool equipOkPressed();

} // namespace CoopDelta

// W2-P7 S-C-A.1 (AMENDMENT P7-6 PR-11): TEST-ONLY world-stream holds (TestServer hold_world_stream / hold_world_adopt),
// inert unless armed; bodies: connectionTCP.cpp beside hold_battle_ready. Never read by game logic before S-C-A.2.
void coopTestHoldWorldStreamArm(bool on);
bool coopTestHoldWorldStreamArmed();
void coopTestHoldWorldAdoptArm(bool on);
bool coopTestHoldWorldAdoptArmed();

// ----- W2-P2 S-C, commit S-C.2: host combat cues (spec (b)11, (b)14) -----
// A cue is bt_ev{kind, actionId, payload}: its STATE effect is the envelope's
// `delta` alone (attached at the CoopEmit::sendEv choke); the payload carries
// only the display fields a later animation unit (W2-P5/P6) needs - frozen here
// (V2), no timing (G1). Every hook below is ONE guarded call at its vanilla
// site and a no-op unless isCoopBattle() && hostSim (so SP, a client and the
// WV-D68 pre-game deaths emit nothing). A cue takes
// CoopArbiter::currentActionId() - 0 outside a context: the hooks serve every
// origin (Q2 = (a)); AI and reaction fire get their own contexts in W2-P3.
// Bodies: connectionTCP.cpp.

/// Spec (b)11: true for the 16 frozen cue kinds (shot, hit, explosion, melee,
/// psi, death, corpse, prime, sync, fall, revive, spawn, panic, prox_trigger,
/// medikit, scanner). The client's CoopApply::applyEvPayload records the cue
/// probe for them and nothing else.
bool coopIsCueKind(const std::string& kind);

/// P1 (ProjectileFlyBState::createNewProjectile, after the hit-log block):
/// the `shot` cue - {actor, unit (=actor), weapon, ammo, action, shotIndex,
/// waypointsLeft, originVoxel, impactVoxel, impact, arc?}. `arc` rides a throw
/// or an arcing shot and comes from coopNoteThrowArc()'s note.
void coopCueShot(const BattleAction& action, const BattleItem* ammo, const Projectile* projectile, int impact);

/// [shotTrajectories] (W2-P5 S-A.1, spec rewrite/prompts/w2p5_display_ghosts.md (b)11) HOST: the last 16
/// `shot` cues coopCueShot() emitted this battle, oldest first, as [{seq, trajLen, speed, impact}] - the
/// trajectory length and speed vanilla's Projectile holds for the shot (Projectile::coopTrajectorySize /
/// coopSpeed), the host-side twin of a combat ghost's trajLen/speed. An empty array on a client and
/// before the first shot. Main thread only (E1 OQ4 = (a)): CoopGhost::reset() only bumps the combat
/// probe generation and this storage is cleared on its next main-thread use. Probe only.
Json::Value coopShotTrajectories();

/// P2 (ProjectileFlyBState::think, after a shotgun pellet's TileEngine::hit):
/// the pellet `hit` cue - {actor?, unit?, voxel, damageType, power, miss:false,
/// pellet}.
void coopCuePellet(const BattleActionAttack& attack, const Position& voxel, int power,
	const RuleDamageType* damageType, int pellet);

/// PR1 (Projectile::calculateThrow, before calculateParabolaVoxel): record the
/// arc of the throw / arcing shot being computed (last write wins inside the
/// `tries` loop); read and cleared by the next coopCueShot(). Nothing is sent.
void coopNoteThrowArc(const Position& originVoxel, const Position& targetVoxel, const Position& deltas,
	double curvature);

/// E1 (end of ExplosionBState::init, before the BA_SELF_DESTRUCT test - the
/// damage is applied by then): `explosion` (area), `melee` (BA_HIT), `psi`
/// (psi amp) or `hit` (a bullet impact), each with its frozen payload.
void coopCueExplosionInit(const BattleActionAttack& attack, const Position& centre, int power, int radius,
	const RuleDamageType* damageType, bool areaOfEffect, bool melee, bool psi, bool miss, int chain,
	const Tile* tile, const BattleUnit* target);

/// D1 (UnitDieBState constructor, after freePatrolTarget()): the `death` cue -
/// {unit, outcome:"dead"|"unconscious", instant, damageType}.
void coopCueDeath(const BattleUnit* unit, const RuleDamageType* damageType);

/// D2 (UnitDieBState::think, before clearUnitSelection()): the `corpse` cue -
/// {unit, pos, corpses:[item ids linked to the unit]}, only when >= 1.
void coopCueCorpse(const BattleUnit* unit);

/// Spec (b)14 (BattlescapeGame::handleNonTargetAction, the last statement of
/// the BA_PRIME and BA_UNPRIME spendTU blocks): prime/unprime as an INSTANT
/// host action - mint, push {id,"host"}, emit the `prime` cue ({actor, unit
/// (=actor), item, fuse, unprime}; delta + h), emit bt_action_end{final, h},
/// pop: the kneel pattern in one call. Coop + hostSim only; logged no-op while
/// another action context is open (the fuse then rides the next delta).
void coopHostPrime(BattleUnit* actor, BattleItem* item, bool unprime);

/// W2-P4 S-D (docs rewrite/prompts/w2p4_client_combat_intents.md, amendment C1
/// PR-Q5 = Q7's mechanism): the host's OWN medi-kit use as an INSTANT host
/// action - ONE call right AFTER the vanilla effect at each of four sites
/// (MedikitState's three buttons, after medikitUse(); ActionMenuState's
/// one-click kit, after its switch - @a medikitAction / @a bodyPart -1 there:
/// the kit's own type decides). Mint, push {id,"host"}, the frozen `medikit`
/// cue {actor, unit (the patient), item, action, bodypart} whose delta carries
/// the TU and the effect, then the close through onChainQuiesced() ->
/// closeBaseContext() (Q10's shared path; a use that left states queued keeps
/// the context open until that chain quiesces). No hook in medikitUse(). Coop +
/// hostSim only; a logged no-op while another action context is open.
void coopHostMedikit(BattleAction* action, BattleUnit* target, int medikitAction, int bodyPart);

/// W2-P4 S-D (PR-Q5): the host's OWN motion-scanner use, the same shape - ONE
/// call right after ActionMenuState's BT_SCANNER spendTU; the frozen `scanner`
/// cue {actor, unit (= actor), item}.
void coopHostScanner(BattleAction* action);

// ----- W2-P3 S-A, commit S-A.2: the `ai` and `endturn` action contexts -----
// Spec rewrite/prompts/w2p3_nonplayer_origins.md (b)1, (b)4-6; amendment B1
// RQ5/RQ6. Each is ONE call at its BattlescapeGame.cpp site and a no-op unless
// isCoopBattle() && hostSim. Origins are host-side action-context values only
// (nothing new on the wire). Bodies: connectionTCP.cpp.

/// V2 (BattlescapeGame::handleAI, the line after the attack's
/// action.updateTU()): open the `ai` context {id, "ai", actor, kind} - kind
/// shoot|throw|launch|melee|psi from @a baType (W2-P2 S-C's mapping) - and arm
/// the W2-P2 arming guard. Every type but psi also records the pre-attack
/// `turn` ev for this action (spec (b)5, RQ6). Logged no-op (bumping
/// `contextBeginRefused`) while another context is open.
void coopBeginAiAttack(BattleUnit* actor, int baType);

/// V3 (handleAI, the statement after the attack's state pushes): end the
/// arming; when @a statesEmpty (every pushed state already popped inside its
/// own push) close the `ai` context now. No-op unless coopBeginAiAttack() armed.
void coopAiAttackPushed(bool statesEmpty);

/// V4 (the first statement of BattlescapeGame::endTurn()): when @a statesEmpty,
/// close EVERY open context (bt_action_end each; an actor-less `endturn` one
/// without `final`), clear the arming and the pre-attack turn flag, and bump
/// the diagnostic `contextsClosedAtEndTurn` for each closed context whose
/// origin is not `endturn` (RQ5). Nothing when states are still queued.
void coopOnEndTurnEntry(bool statesEmpty);

/// V5 (endTurn, before the hot-grenade push loop, @a go = `exploded`) and V6
/// (before each terrain-explosion push, @a go = true): when @a go, open the
/// actor-less {id, "endturn", -1, "endturn"} context the explosion chain runs
/// in; the next endTurn() entry closes it. Logged no-op (bumping
/// `contextBeginRefused`) while another context is open.
void coopBeginEndTurnChain(bool go);

// ----- W2-P3 S-B, commit S-B.2: nested `reaction` / `prox` contexts, D145 -----
// Spec rewrite/prompts/w2p3_nonplayer_origins.md (b)1-3, (b)8, (b)9; amendments
// B1 RQ4 (a) / RQ8, B3 (owner ruling D145 = a), B4; D139. Each is ONE guarded
// call at its vanilla site and a no-op unless isCoopBattle() && hostSim.
// Bodies: connectionTCP.cpp.

/// V13 (TileEngine::tryReaction, the line before the reaction hit-log entry):
/// open the NESTED `reaction` context {id, "reaction", @a reactor, nestedIn: the
/// base's id} - reused for every reactor of the same checkReactionFire burst, a
/// new one per burst (B4) - recording the base action's actor as the reaction's
/// trigger (D145); mark "a reaction against the walker" when @a target is the
/// active walker (its halt reason becomes `reaction`, RQ4 (a)).
void coopBeginReaction(BattleUnit* reactor, BattleUnit* target);

/// V11 (BattlescapeGame::checkForProximityGrenades, the line before the
/// grenade's ExplosionBState push): latch the walk's halt reason `prox`, open
/// the NESTED `prox` context {id, "prox", @a unit} and emit the `prox_trigger`
/// cue {unit, item, pos}.
void coopCueProxTrigger(BattleUnit* unit, BattleItem* item, const Position& pos);

/// D145 (ProjectileFlyBState::init / MeleeAttackBState::init, the reaction
/// target check): the unit a reaction shot's target must be - in coop on the
/// host the unit whose action triggered the reaction (the top-most `reaction`
/// context's trigger); @a selected (vanilla's getSelectedUnit()) everywhere else.
BattleUnit* coopReactionTrigger(BattleUnit* selected);

// ----- W2-P3 S-C, commit S-C.2: units that appear mid-battle -----
// Spec rewrite/prompts/w2p3_nonplayer_origins.md (b)9-(b)12; amendment B1
// RQ2/RQ9/RQ10/RQ11. The unit itself rides the delta's `unitsAdded` (the
// host's BattleUnit::save() record, materialized on the client through the
// battle-load path) and its special built-in weapons ride `itemsAdded`; these
// hooks only announce it. Each is ONE guarded call at its vanilla site and a
// no-op unless isCoopBattle() && hostSim. Bodies: connectionTCP.cpp.

/// V16 (SavedBattleGame::convertUnit, the line after newUnit->dontReselect(),
/// cause "convert", @a from = the converted unit) and V12
/// (BattlescapeGame::spawnNewUnit, the line after the new unit's
/// calculateFOV(), cause "item", @a from null): the frozen `spawn` cue
/// {unit, cause, from?} in the running action context (0 outside one).
void coopCueSpawn(BattleUnit* unit, const char* cause, const BattleUnit* from);

/// V17 (NextTurnState's ctor, the line after determineReinforcements()): one
/// `spawn` cue {unit, cause} per live unit the delta snapshot does not know
/// yet - the ids are listed BEFORE the first cue is sent, whose delta then
/// carries every one of them in `unitsAdded`.
void coopCueSpawnAdded(SavedBattleGame* save, const char* cause);

// ----- W2-P3 S-D, commit S-D.2: the turn machine's own chains -----
// Spec rewrite/prompts/w2p3_nonplayer_origins.md (b)1, (b)7, (b)9 (V9, V10,
// V14, V15). Each is ONE guarded call at its vanilla site and a no-op unless
// isCoopBattle() && hostSim. `panic` is a base action context (host-side value
// only, nothing new on the wire); `fall` and `revive` open no context and carry
// the running one's id (0 outside a chain). Bodies: connectionTCP.cpp.

/// V9 (BattlescapeGame::handlePanickingUnit, the line before the flee walk's
/// UnitWalkBState push): open the `panic` context {id, "panic", @a unit} when
/// no context is open, then expand the live Pathfinding exactly as
/// CoopArbiter::beginAiWalk() does and open the walk chain under the panic id
/// (origin "panic", kind `walk`) - the flee streams `walk_step` evs and the
/// panic's bt_action_end carries the completion restate.
void coopNotePanicFleeWalk(BattleUnit* unit, SavedBattleGame* save);

/// V10 (handlePanickingUnit, the line before the UnitPanicBState push): ensure
/// the `panic` context (opened by V9 for a flee) and emit the frozen `panic`
/// cue {unit, mode}: "berserk" for STATUS_BERSERK, else "flee" when @a flee,
/// else "freeze". It is the action's first ev; its delta carries the weapons
/// a flee dropped.
void coopCuePanic(BattleUnit* unit, bool flee);

/// W2-P5 S-T.2 (amendment E3.1 ST3 / OR2 / OR3, owner D151 = (b); UnitPanicBState::think,
/// the line before the berserk shot's UnitTurnBState push): on the co-op HOST, inside
/// @a unit's own `panic` context, arm the pre-action flag so that turn emits the wave-1
/// `turn` ev (the watching machine animates it) - only when the unit must turn toward
/// @a target (OR3 (a)). A no-op in single player and on a client.
void coopArmBerserkTurn(BattleUnit* unit, const Position& target);

/// V14 (UnitFallBState::init, its last statement): the frozen `fall` cue
/// {units:[{unit, from}]} for SavedBattleGame::getFallingUnits() at init,
/// `from` = each unit's position then; no cue when the list is empty.
void coopCueFall(SavedBattleGame* save);

/// V15 (SavedBattleGame::reviveUnconsciousUnits, the line after
/// removeUnconsciousBodyItem()): the frozen `revive` cue {unit, pos}, pos after
/// placeUnitNearPosition(). Emitted inline (spec (b)9), also inside
/// SavedBattleGame::endTurn() before the side_transition.
void coopCueRevive(BattleUnit* unit);

// ----- W2-P4 S-C, commit S-C.2: a partner's melee on the host -----
// Spec rewrite/prompts/w2p4_client_combat_intents.md, amendment C1 PR-Q4. Body:
// connectionTCP.cpp, next to coopLatchActionResult().

/// PR-Q4 (MeleeAttackBState::think, ONE guarded term on the "not a reaction
/// attack" condition that sets the parent's current action to BA_NONE): TRUE on
/// the co-op HOST while the base action context is a partner's `intent` and
/// @a action's actor is that context's actor, so a partner's melee never resets
/// the HOST player's own _currentAction (its aim mode) - the same REMOTE test as
/// coopLatchActionResult(), without its latch. FALSE everywhere else (SP, a
/// client, the host's own and the AI's actions), so vanilla is byte-identical
/// there. No side effect.
bool coopIsRemoteIntentAction(const BattleAction& action);

// ----- W2-P4 S-E1, commit S-E1.2: whose force-fire key a shot reads -----
// Spec rewrite/prompts/w2p4_client_combat_intents.md (b)8 (F423, the per-player
// half; R3.2 F1-F4). Body: connectionTCP.cpp, next to coopIsRemoteIntentAction().

/// The force-fire key of the player whose action is running - ONE guarded call
/// replacing vanilla's `Options::forceFire && save->isCtrlPressed(true)` at each
/// of the four force-fire terms (ProjectileFlyBState::init, Projectile.cpp x2,
/// TileEngine::isTileInLOS). On the co-op HOST while the base action context is
/// a partner's `intent`, it is that order's own `forceFire` (the ordering
/// machine's Options::forceFire && its own Ctrl, shipped on the `shoot` order;
/// false for every other intent kind) - never the host's option or keys. Every
/// where else (SP, a client, the host's own and the AI's actions) it is
/// vanilla's own expression, so vanilla is byte-identical there. No side effect.
bool coopForceFirePressed(const SavedBattleGame* save);

// ----- W2-P6b S-L, commit S-L.1: the hit-log mirror probe (owner D172 (a)) -----
// Spec rewrite/prompts/w2p6_display_two.md AMENDMENT P6-5 section 6, AMENDMENT P6-6 section 5 and ruling SL-1. Body:
// connectionTCP.cpp, right after coopShotTrajectories() (the probe storage, outside every RW-REPLAY-REGION).

/// [hitLogMirror] the event_state probe of THIS machine: {noted, sent, applied, localSuppressed, pending, dropped,
/// last: [the last 32 entries {seq, t, f, k?}]}. HOST: `noted` = hit-log entries recorded after vanilla's player-side
/// check, `sent` = entries attached to an outermost emit (counted per entry, not per envelope), `pending` = the size of
/// the list waiting for the next emit, `last` = the entries sent with their carrying seq. CLIENT: `applied` = entries
/// appended from an applied envelope, `localSuppressed` = its own ActionMenuState PLAYER_FIRING appends skipped, `last`
/// = the entries applied with their carrier's seq. `dropped` = entries discarded before they were sent or applied.
/// `t` = HitLogEntryType, `f` = UnitFaction, `k` = [the weapon type] for PLAYER_FIRING, [the message keys] for
/// NEW_TURN_WITH_MESSAGE, absent otherwise. S-L.1 added the storage; S-L.2's four functions below write it.
/// Main thread only; battle-scoped (cleared on the first use after CoopGhost::reset() bumps the combat generation).
Json::Value coopHitLogMirrorProbe();

// ----- W2-P6b S-L, commit S-L.2: the hit log on both machines (owner D172 (a)) -----
// Spec rewrite/prompts/w2p6_display_two.md AMENDMENT P6-5 section 6 (the five vanilla lines; Q3 (a) the envelope
// carrier, Q4 (a) the client's appendToHitLog), AMENDMENT P6-6 section 5 (Q2 (a)). Body: connectionTCP.cpp, right
// after coopHitLogMirrorProbe() (outside every RW-REPLAY-REGION). The host's sendEv attaches the pending list as the
// envelope field `hitLog`; the client applies it right after CoopReveal::applyFrom() in CoopDisplayQueue::onApplied().

enum HitLogEntryType : int; // Savegame/HitLog.h
enum UnitFaction : int;     // Mod/Unit.h

/// SavedBattleGame::appendToHitLog (both overloads), right after vanilla's append (so only an entry that passed the
/// player-side check): on the co-op HOST (`hostSim`) of a battle in phase Handshake or Active (P6-6 Q2 (a)) it records
/// the entry {t, f, k?} - `k` = the pending key(s) for PLAYER_FIRING / NEW_TURN_WITH_MESSAGE - in the pending list
/// that rides the next outermost emit, then clears the pending keys. A no-op on a client and in single player.
void coopHitLogNote(HitLogEntryType type, UnitFaction faction);

/// ActionMenuState, above vanilla's PLAYER_FIRING append as `if (coopHitLogPlayerFiring(...)) {} else`: on a co-op
/// CLIENT TRUE - the local append is skipped, the host's entry replaces it (V7; `localSuppressed` +1); on the co-op
/// HOST it sets the pending weapon key and returns FALSE (vanilla appends, coopHitLogNote records the key); single
/// player FALSE with no side effect.
bool coopHitLogPlayerFiring(const std::string& weaponType);

/// NextTurnState's environment block (it runs on the host only: the client skips the block): sets the pending message
/// keys (the non-empty of `a`, `b`) for the NEW_TURN_WITH_MESSAGE entry the constructor appends next. A no-op off the
/// co-op host.
void coopHitLogMessageKeys(const std::string& a, const std::string& b);

// ----- W2-P6a S-M, commit S-M.2: the battle messages on the HOST (owner D132) -----
// Spec rewrite/prompts/w2p6_display_two.md `## P6a PINNED STAGE TEXT` (b)1, the W2-P6a plan review section 4 (OR1 (a)),
// AMENDMENT P6-5 section 3. Body: connectionTCP.cpp, right after the CoopBattleUi namespace (the message store).

/// The co-op HOST's decision at each of vanilla's eleven unit-message pushes (UnitDieBState x3, BattlescapeGame x8),
/// inserted above the unchanged push as `if (coopHostDivertUnitMessage(...)) {} else` (OR1 (a)). FALSE at once outside
/// a co-op battle and on a client: vanilla pushes. On the host it records the message (event_state `messages`) and
/// returns TRUE only when @a about - the unit the message is ABOUT - is the PARTNER's (another seat of this seat's
/// faction): the text then shows as vanilla's fading WarningMessage notice on the live BattlescapeState (nothing for
/// the invisible pause, @a key "") and the push is skipped, so the shared battle never pauses for the other player's
/// soldier. This machine's own units and units no player owns (D170 (a)) keep vanilla's box. @a named is the unit
/// whose gender and name the text carries (nullptr for the psi texts, which take none). Writes no unit field: every
/// setNotificationShown() stays vanilla's.
bool coopHostDivertUnitMessage(const BattleUnit* about, const char* key, const BattleUnit* named);

// ----- W2-P6a S-C, commit S-C.2: the camera on the HOST (owner D131) -----
// Spec rewrite/prompts/w2p6_display_two.md `## P6a PINNED STAGE TEXT` (c)1, the W2-P6a plan review section 4 (ST1 (a)),
// AMENDMENT P6-5 section 4 C-C1. Body: connectionTCP.cpp, right after coopThinkCoveredBattle() (the same origin test).

/// The co-op HOST's guard at vanilla's five camera writes a partner's action reaches - the projectile follow
/// (ProjectileFlyBState::init, @a what "follow"), the explosion centre and the hit view level (ExplosionBState::init,
/// "explosion" / "hitLevel"), the walker view level (UnitWalkBState::think, "walkLevel") and the panic centre
/// (BattlescapeGame::handlePanickingUnit, "panic"). Each sits LAST in its vanilla condition (or as `if (...) {} else`
/// above an unconditional write), so it is evaluated only when vanilla would move the camera. FALSE at once outside a
/// co-op battle and on a client: vanilla moves the camera. On the host it is TRUE - the write is skipped and the
/// probe's `camera.suppressed[what]` +1 - iff the action context stack's FRONT (base) entry has origin `intent` (the
/// partner's order and everything nested in it, reactions and prox included; a lone nested entry counts by the base
/// origin it carries) or @a actor is commanded by the partner's seat (another seat of this seat's faction: a panic, a
/// berserk, a reaction shot by the partner's soldier). The `intent` term applies only in co-op (gamemode not 2/3).
/// In PvP every intent is the opponent's order (SC-5): only the partner term applies, never true with one seat per side.
/// An `endturn` base is never suppressed (OR5 (a)). Writes no battle state.
bool coopHostPartnerCamera(const BattleUnit* actor, const char* what);

} // namespace OpenXcom
