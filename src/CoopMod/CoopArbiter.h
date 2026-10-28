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

#include <cstdint>
#include <string>
#include <vector>

#include <json/json.h>

#include "../Battlescape/Position.h"

namespace OpenXcom
{

class BattleUnit;
class BattlescapeGame;
class Game;             // the covered-battle driver's parameter
class SavedBattleGame;
class RuleSkill; // coopInterceptSkillUse()
struct BattleAction;
struct BattlescapeTally; // coopAbortDialogTally()'s result (BattlescapeGame.h)
class Inventory;        // the inventory execution-point guards
class BattlescapeButton; // the pre-battle OK button (the ready toggle)
class BattleItem;
class RuleInventory;
struct BattleActionCost;
class EquipmentLayoutItem; // the pre-battle bulk tools' layouts
class BattlescapeState; // coop: coopEquipCycleView()'s vanilla PREV / NEXT
class Surface;          // coop: coopEquipApplyViewLook()'s buttons
class Text;             // coop: coopEquipApplyViewLook()'s owner line

/**
 * The walk intent's plan fields, handed to sendClientIntent() below.
 *
 * Kept as a struct rather than six more scalar defaults on that signature
 * because the rule is "one function, two callers - EXTEND the signature,
 * never fork it", and a struct is how the signature grows without turning into
 * a positional-argument minefield for the turn/kneel callers that pass none of
 * it.
 *
 * `dest` is the tile the ordering seat CLICKED (the value it handed to
 * Pathfinding::calculate), NOT necessarily the last tile of `path`: a reserve
 * truncation ships a shorter prefix, and the wire's `dest`
 * then names that prefix's own endpoint so the plan stays self-consistent.
 * `pathOverride`, when non-empty, REPLACES the client's own previewed path -
 * it exists only for the `battle_intent` lever's `path` argument, which is how
 * a test ships a deliberately-blocked plan for the `path_changed`
 * deny. Nothing in the game ever sets it.
 */
struct CoopWalkIntentArgs
{
	Position dest;
	bool run = false;
	bool strafe = false;
	bool sneak = false;
	bool ignoreSpotted = false;
	std::vector<Position> pathOverride;
};

/**
 * The COMBAT intent's plan, handed to sendClientIntent() below - the one plan
 * struct the "extend the signature, never fork it" rule allows beside
 * CoopWalkIntentArgs. The `shoot` kind (snap / aimed / auto) uses:
 *   action      the wire action string ("snap" | "aimed" | "auto")
 *   weapon      the item id of the weapon the order fires
 *   ammo        getAmmoForAction(type)'s item id when the order was built, -1 none
 *   target      the clicked tile
 *   targetUnit  the unit the order aims at (-1 = a tile)
 *   targetPos   that unit's position when the order was built (iff targetUnit >= 0)
 *   forceFire   the ORDERING machine's own Options::forceFire && Ctrl
 * Everything here is PLAN data: a busy-held order keeps it verbatim and only
 * `tuBasis` is recomputed at the resubmit, which is why tuBasis is not
 * a member.
 *
 * the same plan carries the `throw` and `prime` kinds
 * and the launcher's `shoot` (action "launch"); for those `weapon` is the item
 * the order uses (the wire's `item` for throw / prime):
 *   waypoints   the launcher's waypoint tiles in click order (action "launch")
 *   fuse        the chosen fuse (prime; -1 with unprime)
 *   unprime     true for BA_UNPRIME (the `prime` kind's `unprime` field)
 *
 * the same plan carries the `melee`, `psi` and
 * `use_item` (mind probe) kinds; `weapon` is the stun rod / psi amp / probe
 * (the wire's `item` for use_item), `action` the psi action ("panic" | "mc" |
 * "use"), `target` the melee tile validMeleeRange() gave (the clicked tile for
 * psi, the target unit's tile for the probe), `targetUnit` / `targetPos` the
 * unit the order acts on, and:
 *   terrainPart the melee's terrain part (validTerrainMeleeRange(); 0 = none)
 *
 * the same plan carries the `medikit`, `use_item`
 * (scanner), `reload` and `reaction_hands` kinds. For `medikit`, `weapon` is
 * the kit (the wire's `item`), `action` the button ("heal" | "stim" |
 * "painkiller"), `targetUnit` / `targetPos` the patient, and:
 *   bodypart    the body part the button treats (UnitBodyPart; the torso for
 *               stimulant and painkiller)
 * For the scanner `weapon` is the scanner; `reload`'s plan is empty; for
 * `reaction_hands` `action` is the hand ("left" | "right") and:
 *   ctrl        the ORDERING machine's Ctrl at the press
 *
 * the spray autoshot is a `shoot` with action "auto"
 * and:
 *   spray       the shot VOXELS of vanilla primaryAction's own spread, in the
 *               action's list order (back = the first shot); targetUnit -1
 *
 * The same plan carries the `skill`
 * kind (a SkillMenuState row: `weapon` is the item chooseWeaponForSkill()
 * picked, -1 = none; the wire's `action` is the skill's target mode, read off
 * the skill's own rule) and, on EVERY kind, the skill a follow-up order runs
 * under:
 *   skill       the RuleSkill type (empty = none): for a `skill` order the row
 *               pressed; for any other kind this machine's
 *               _currentAction.skillRules when the order was built (a
 *               follow-up of a `continue: true` skill), so the host charges the
 *               skill's cost (the updateTU() rule)
 */
struct CoopCombatIntentArgs
{
	std::string action;
	int weapon = -1;
	int ammo = -1;
	Position target;
	int targetUnit = -1;
	Position targetPos;
	bool forceFire = false;
	std::vector<Position> waypoints;
	std::vector<Position> spray;
	int fuse = -1;
	bool unprime = false;
	int terrainPart = 0;
	int bodypart = -1;
	bool ctrl = false;
	std::string skill;
	// The `inv_move` plan. `action` carries the op (move|load|unload) and `weapon` the
	// item (as for throw / prime); these carry the move's target section and
	// cell, the load's weapon and its Shift quick-swap.
	std::string invSlot;
	int invX = 0;
	int invY = 0;
	int invWeapon = -1;
	bool invSwap = false;
	// The `rename` order's new name (the name field's whole text).
	std::string name;
	// The `gift` order's target seat.
	int giftSeat = -1;
	// the
	// `inv_bulk` plan. `action` carries the op (apply|clear|autoequip|save_personal|save_global); these
	// carry its layout (`template`: apply and the two saves) and the global layout slot (`index`: save_global).
	Json::Value invTemplate;
	int invIndex = -1;
	// a layout SAVE's armor half as the saving machine's vanilla
	// save stored it (`armor`: an armor type, empty = none) and a save-dialog save_global's slot name (`name`; null =
	// none rides: a Ctrl+digit save leaves the name, as vanilla).
	std::string invArmor;
	Json::Value invName;
};

/**
 * The HOST-side admission arbiter. Every bt_intent lands here (via the lane
 * dispatcher in connectionTCP.cpp's onTCPMessage) and is either admitted
 * (executed immediately + bt_ack) or denied (bt_deny{reason}, one of the
 * wire's machine enum strings). Deny-only: NO host-side queue exists - a
 * denied client holds / resubmits. Kept behind this one seam (onIntent) so a
 * 1-slot host queue could be added later without touching the wire.
 *
 * Bodies live in connectionTCP.cpp, next to BattleAuthority/CoopIdMaps/
 * CoopPump/CoopEmit.
 */
namespace CoopArbiter
{

/// Host: the lane dispatcher calls this with one parsed bt_intent envelope
/// ({state, iseq, seat, actorId, kind, ...concrete-plan fields}).
/// Resolves the actor, checks not_your_unit / turn_over / busy, then
/// dispatches to validateTurn()/validateKneel() for the kind-specific
/// cost/well-formedness checks. On a clean pass: mints an actionId, ACKs
/// (CoopWire::makeAck), pushes an action context, and executes immediately
/// (a reproduction of vanilla's turn for turn, a direct kneel() wrap for
/// kneel). On any check failing: denies (CoopWire::makeDeny) and returns - no
/// host-side queue. No-op (logs) outside an active coop battle or
/// with no live SavedBattleGame.
void onIntent(const Json::Value& intent);

/// Host: quiescence hook - called (via the coopOnChainQuiesced()
/// free-function forwarder below) from BattlescapeGame::popState() at the
/// exact point the popped BState chain leaves _states empty. If a coop
/// action context is on top of the stack, emits the pending bt_action_end
/// for the just-finished chain-ful action (turn) and pops the context,
/// clearing this battle's "chain busy" state so the next intent can be
/// admitted. No-op if the action-context stack is empty (a popState with no
/// coop action in flight - e.g. a foreign/AI chain) or outside an active coop
/// battle.
void onChainQuiesced();

/// Host: origin stamping for a coop HOST's own local turn (host-local
/// player input never enters the intent path - it always runs
/// vanilla directly, never onIntent()). Called from the THIN
/// BattlescapeGame::secondaryAction hook site's own-input branch,
/// BEFORE it pushes UnitTurnBState, mirroring onIntent()'s turn-branch
/// bookkeeping (mint actionId, push {actionId,"host"} action context, record
/// @a actor as this chain's pending actor plus its pre-turn direction/
/// turret-direction) so UnitTurnBState::think()'s completion hook
/// (coopOnUnitTurnFinished below) and onChainQuiesced()'s bt_action_end emit
/// both fire correctly for the host's OWN turns too, exactly as they already
/// do for an admitted remote intent. No-op outside an active coop battle (the
/// vanilla call site stays a single unconditional call, like
/// coopOnChainQuiesced()).
void beginHostLocalTurn(BattleUnit* actor, bool turret);

/// Host: origin stamping for a coop HOST's own local kneel - the
/// chain-less counterpart to beginHostLocalTurn() above. Called
/// from the THIN BattlescapeState::btnKneelClick hook site's own-input
/// branch, BEFORE it calls BattlescapeGame::kneel(bu), mirroring
/// onIntent()'s "kneel" branch bookkeeping (mint actionId, push
/// {actionId,"host"} action context, record @a actor as this kneel's
/// pending actor) so the THIN emit hook inside BattlescapeGame::kneel()
/// itself (coopOnKneelFinished below) fires correctly for the host's OWN
/// kneel too, exactly as it already does for an admitted remote intent. No
/// BState/quiescence involved (kneel resolves synchronously inside
/// the single kneel() call this begins). No-op outside an active coop
/// battle (the vanilla call site stays a single unconditional call, like
/// beginHostLocalTurn()).
void beginHostLocalKneel(BattleUnit* actor);

/// Origin stamping for a coop HOST's own local walk -
/// the chain-ful counterpart of beginHostLocalTurn() above, called from the
/// THIN BattlescapeGame::primaryAction walk-confirm hook site's own-input
/// branch BEFORE it pushes UnitWalkBState. Mints an actionId, pushes
/// {actionId,"host"}, records @a actor as this chain's pending actor and
/// @a path as the plan the step hook and the completion restate report
/// against. No-op outside an active coop battle.
void beginHostLocalWalk(BattleUnit* actor, const std::vector<Position>& path);

/// The AI-origin sibling of beginHostLocalWalk() above - BA_WALK ONLY.
/// Expands the plan from the LIVE Pathfinding itself, so the vanilla call site in handleAI() stays a single
/// unconditional call. No-op outside an active coop battle and on a client.
/// Nothing new goes on the wire: origin "ai" is observable only
/// through the host's event_state.lastWalk.origin.
void beginAiWalk(BattleUnit* actor, SavedBattleGame* save);

/// Origin stamping for a coop HOST's own combat action - shot (snap/
/// aimed/auto/spray), throw, launch, psi, melee (@a baType = the vanilla
/// BattleActionType). Mints an actionId, pushes {actionId,"host"}, records
/// @a actor as the chain's pending actor with the chain kind shoot|throw|
/// launch|psi|melee, bumps `hostCombatContexts`. The chain's end is the existing
/// onChainQuiesced() bt_action_end; the cue hooks (CoopDelta.h) carry this id.
/// Called from BattlescapeGame (after the primaryAction.spray/.fire and
/// launchAction tripwires, before the PsiAttackBState/MeleeAttackBState pushes)
/// and from the TestServer battle_fire command (which bypasses primaryAction).
/// No-op outside a coop battle, on a client, without an actor; logged no-op
/// while another action context is open.
void beginHostLocalCombat(BattleUnit* actor, int baType);

/// The ARMING GUARD around a turn-then-shot
/// push pair whose first push can pop inside itself (UnitTurnBState on a unit
/// already facing its target) and run onChainQuiesced() before the shot state
/// exists. beginChainArming() (host, coop only) right after the context
/// begins; while armed onChainQuiesced() defers (logged, `armingDeferrals` +1);
/// endChainArming(@a statesEmpty = the BState queue is empty after the second
/// push) clears it and, when nothing is left running, closes the context
/// itself. The battle_fire command and handleAI use it.
void beginChainArming();
void endChainArming(bool statesEmpty);

/// Test/introspection (TestServer event_state `lastWalk`): the most recent walk
/// this machine EMITTED (host) or APPLIED (client), as
/// {actionId, unit, steps:[{stepIndex, from, dir, to, tuAfter, enAfter, seq}],
///  path:[{x,y,z}], halted, reason, final}. `path`/`halted`/`reason`/`final`
/// appear once the completion bt_action_end has been emitted/applied. Null
/// before the first walk of a battle. The ONLY way a test can see the walk's
/// per-step payload at all: CoopEventLog is a fixed POD ring and deliberately
/// carries no payload (BattlePump.h).
Json::Value lastWalk();

/// Test/introspection (TestServer event_state `lastSpot`): the most
/// recent `spot` ev this machine EMITTED (host) or APPLIED (client), as
/// {actionId, unit, seen:[uid...], haltStep, seq}. Null before the first spot
/// of a battle. Same justification as lastWalk above - CoopEventLog carries no
/// payload, so this is the only window onto `seen`/`haltStep`.
Json::Value lastSpot();

// TEST-ONLY (minimal, deterministic; same family and the same removal note
// as requestDeferIntents() below).
/// HOST: arm a ONE-SHOT latch that halts the next walk at its NEXT completed
/// step boundary, exactly as if vanilla had taken one of its own
/// cancelCurentMove() branches. The step evs already emitted STAND
/// and the completion bt_action_end carries the executed prefix plus
/// `halted:true` + `reason`. Without it a halt mid-walk is not drivable at all:
/// walk-core's fixtures are door- and contact-free by construction and
/// its own TU/energy guards need a unit engineered to run out mid-path.
void requestHaltWalk();

/// TEST-ONLY: arm a one-shot latch that halts the
/// next walk BEFORE its first step, so it executes ZERO steps.
/// requestHaltWalk() above cannot express that - it is consumed at a COMPLETED
/// step - and a zero-step walk is precisely the case in which no `bt_ev` carries
/// the actor, so the client cannot resolve bt_action_end's `final`.
void requestHaltWalkBeforeStep();

/// Test/introspection (TestServer `event_state`): the client-side reserve
/// rule, counted. `walkReserveRefusals()` is how many walk intents THIS
/// machine's own TU reserve stopped at step 1 - nothing went on the wire, and
/// vanilla's own reserve warning was raised by the very checkReservedTU() call
/// that returned false. `walkReserveTruncations()` is how many plans it
/// SHORTENED to a k-1 prefix before shipping. Both exist so the step-1 case is
/// a POSITIVE assertion about the reserve rule instead of an absence that any
/// unrelated failure would also produce. Battle-scoped, like the rest of this
/// namespace's state.
int walkReserveRefusals();
int walkReserveTruncations();

/// Pushes {actionId, origin} onto CoopMod's own action-context stack
/// (no BState code stores coop state). @a origin is one of the wire's
/// origin enum strings ("ai | endturn | reaction | panic | script | prox |
/// host | intent"); "host" is reserved for the host-seat's own direct input
/// (the emit hooks). The arbiter's own admitted-intent push sites use
/// "intent".
void pushActionContext(std::uint32_t actionId, const char* origin);

/// The actionId on top of the action-context stack, or 0 if the stack is
/// empty (0 is never a minted actionId, so 0 doubles as "none").
std::uint32_t currentActionId();

/// The `origin` string on top of CoopMod's action-context stack, or
/// "" when the stack is empty. The wire's enum values; "intent" means the action
/// was ADMITTED FROM A CLIENT's bt_intent (the arbiter's own push sites),
/// which is what the client-origin rules key on.
const char* currentActionOrigin();

/// Turn validator: cost + well-formedness only. not_your_unit/turn_over/busy
/// need the intent's seat and the live BattlescapeGame, which this signature
/// does not carry, so onIntent() checks them itself ahead of this call.
/// Returns nullptr if @a toDir/@a turret/@a tuBasis admit cleanly against
/// @a unit's current state; otherwise one of the wire's deny reason enum
/// strings (never an ad-hoc string).
const char* validateTurn(const BattleUnit* unit, int toDir, bool turret, int tuBasis);

/// Kneel validator, same contract/caveat as validateTurn().
const char* validateKneel(const BattleUnit* unit, bool kneel, int tuBasis);

/// Walk validator. Same contract as
/// validateTurn()/validateKneel(): returns nullptr when @a intent admits
/// cleanly, else one of the wire's deny reason enum strings - here only
/// `path_changed` or `cost_changed`, the two names for "this concrete
/// plan is no longer the plan the host would execute".
///
/// UNLIKE the other two it needs the LIVE battle, so it takes the parsed
/// envelope instead of scalar plan fields: the walk's `path` is a CONCRETE PLAN,
/// and validating it means walking it tile-by-tile against CANONICAL occupancy
/// through the host's own Pathfinding::getTUCost - which is also where the
/// recomputed `tuBasis` (Sigma per-step getTUCost(bam), never the A* route
/// cost) and the energy total come from. It ALSO re-runs
/// Pathfinding::calculate() for @a unit and proves the host's own route is
/// tile-for-tile the shipped one, which is what lets the caller execute
/// through vanilla's UnitWalkBState with NO silent reroute: the path the host
/// walks has been proven equal to the path the wire carried, or the intent was
/// denied (no silent reroute / truncation / no-op - ever).
///
/// On a clean pass @a outPath receives the validated tile list, @a outTuCost /
/// @a outEnergyCost the recomputed totals, and the host's Pathfinding is left
/// holding exactly that route, ready for UnitWalkBState.
const char* validateWalk(BattleUnit* unit, const Json::Value& intent,
	std::vector<Position>& outPath, int& outTuCost, int& outEnergyCost);

// ----- CLIENT section -----

/// CLIENT: the shared intent-building function - "one function, two callers".
/// Builds a bt_intent envelope (CoopWire::makeIntent) from EXPLICIT
/// plan fields, mints this machine's client-local iseq (this namespace's own
/// counter - separate from the HOST-side actionId mint above; reset at the
/// same battle-teardown chokepoint), computes @a kind's tuBasis the same way
/// the client preview would (turn: Sigma per-tick getTurnCost/1-per-tick-if-
/// turret over the shortest-arc tick count, mirroring validateTurn()'s own
/// recompute; kneel: getKneelChangeCost()) UNLESS @a tuBasisOverride is >= 0,
/// in which case it REPLACES the recomputed basis (a test's stale-basis
/// override). Ships via CoopEmit::sendBattle - never touches the
/// host-side action-context stack or executes anything locally (turn
/// EXECUTION is not built here; this only builds and sends the envelope) - the
/// admitted intent's real execution happens on the HOST machine, inside
/// onIntent() above, exactly like any other bt_intent sender).
///
/// Caller #1: TestServer's battle_intent command. Caller #2:
/// the UI intercepts (BattlescapeGame::secondaryAction /
/// BattlescapeState::btnKneelClick) - PLACE new callers here, never a second
/// copy of the envelope-building logic.
///
/// @a kind is "turn" or "kneel". @a toDir/
/// @a turret apply to "turn"; @a kneel applies to "kneel". Returns the minted
/// iseq, or 0 on failure (0 is never a valid iseq a caller should treat
/// as sent) - outside an active coop battle, with no live SavedBattleGame,
/// if @a actorId does not resolve on THIS machine, or for an unknown @a kind.
///
/// Following the "extend the signature, never fork it" rule:
/// @a kind may now also be "walk", in which case @a walk carries the plan (see
/// CoopWalkIntentArgs above) and MUST be non-null. The walk branch previews the
/// concrete path itself through the LOCAL Pathfinding (unless
/// @a walk->pathOverride is set), computes `tuBasis` as Sigma per-step
/// getTUCost(bam), and applies the CLIENT-SIDE RESERVE RULE before the
/// envelope is built: `BattlescapeGame::checkReservedTU` is evaluated per step
/// over the previewed path with THIS machine's own getTUReserved()/
/// getKneelReserved(), a violation at step 1 sends NOTHING (returning 0, with
/// vanilla's own reserve warning already on screen because that first check is
/// made with justChecking=false), and a violation at step k>1 ships the k-1
/// prefix with `tuBasis` over that prefix only.
///
/// @a kind may also be "shoot", in which case @a combat
/// carries the plan (CoopCombatIntentArgs above) and MUST be non-null; `tuBasis`
/// is the actor's own getActionTUs(type, weapon).Time unless
/// @a tuBasisOverride is given. Every send is counted per kind in
/// intentsSent().
///
/// @a kind may also be "throw" (BA_THROW) or "prime"
/// (BA_PRIME, or BA_UNPRIME when @a combat->unprime), and "shoot" may carry the
/// action "launch" with its waypoints; each takes @a combat the same way, and
/// `tuBasis` is getActionTUs() of that kind's action type and item.
/// + "melee" (BA_HIT), "psi" (BA_PANIC / BA_MINDCONTROL / BA_USE by
/// the plan's action) and "use_item" (BA_USE: the mind probe).
/// "use_item" also carries the motion scanner; + "medikit" (BA_USE
/// with the kit), "reload" and "reaction_hands" (neither has an action type,
/// so neither ships a `tuBasis`).
/// + "skill" {skill, action (the skill's target
/// mode), weapon, tuBasis = getActionTUs(target mode, skill).Time}; and every
/// combat kind whose @a combat->skill is set ships it as `skill` with its
/// `tuBasis` from getActionTUs(type, skill) (the updateTU() rule).
std::uint32_t sendClientIntent(const char* kind, int actorId, int toDir = -1,
	bool turret = false, bool kneel = false, int tuBasisOverride = -1,
	const CoopWalkIntentArgs* walk = nullptr, const CoopCombatIntentArgs* combat = nullptr);

/// CLIENT: host bt_ack{iseq,actionId} receipt - if
/// @a ack's iseq matches this client's own in-flight intent (set by a prior
/// sendClientIntent() call that actually shipped), records the actionId so a
/// later bt_action_end (which carries no unit/iseq of its own, only
/// actionId) can be recognized as "mine" by onActionEndApplied()
/// below. No-op if the iseq does not match (a stale/foreign ack, or nothing
/// in flight) or outside an active coop battle.
void onAck(const Json::Value& ack);

/// CLIENT: host bt_deny{iseq,reason} receipt - always updates
/// lastDeny() below (event_state's own field) and shows the
/// CoopBattleUi::showDeny() banner; additionally clears this client's own
/// in-flight lock if @a deny's iseq matches it. No-op (does not even update
/// lastDeny) outside an active coop battle.
///
/// reason=="busy" on THIS client's own in-flight intent does not drop it:
/// the plan is moved into the PENDING slot, CoopBattleUi::showPending()
/// raises the busy banner, and it is auto-resubmitted at the next
/// event_state-visible quiescence (see onQuiescenceObserved() below). Every
/// OTHER deny reason shows the banner and drops the intent.
void onDeny(const Json::Value& deny);

/// CLIENT: called by CoopDisplayQueue::onApplied()
/// (BattlePump.h/connectionTCP.cpp) once a bt_action_end has been applied -
/// clears this client's own in-flight lock if @a actionId matches it (the
/// acted-upon unit becomes send-able again via sendClientIntent()). No-op
/// for a foreign actionId (this client did not initiate it, e.g. it belongs
/// to another seat or to the host's own local input) or if nothing is in
/// flight.
void onActionEndApplied(std::uint32_t actionId);

/// event_state's lastDeny field: the {iseq,reason} object from the most
/// recent onDeny() this CLIENT machine received this battle, or
/// Json::Value() (null) if none yet.
Json::Value lastDeny();

// ----- CLIENT auto-retry + info-cancel -----

/// CLIENT: called by CoopDisplayQueue::onApplied() for every applied
/// bt_action_end, AFTER onActionEndApplied() has resolved this client's own
/// in-flight lock. This is the "event_state-visible
/// quiescence" signal: the host emits bt_action_end only from
/// onChainQuiesced(), so applying one is exactly the client-visible
/// proof that the blocker's chain has unwound. If a PENDING intent is held,
/// it is resubmitted here through sendClientIntent() - which RECOMPUTES the
/// preview + tuBasis against CURRENT client state, never
/// replays a stale basis. A resubmit that is busy-denied again simply goes
/// pending again (self-sustaining until it is admitted, cancelled by policy,
/// or cancelled by the user). No-op outside an active coop battle or with
/// nothing pending.
void onQuiescenceObserved();

/// CLIENT: the info-cancel policy evaluation point - called by
/// CoopDisplayQueue::onApplied() for every applied bt_ev, AFTER the payload
/// has been applied (so the visibility-gain check reads post-apply state).
/// Evaluates the four Options:: toggles (coopCancelOnEnemySpotted /
/// OwnUnitHit / VisibilityGain / AnyPartnerAction), read LIVE, against @a ev
/// and cancels the pending intent via
/// CoopBattleUi::showCancel() naming the trigger (never a generic
/// message). @a visibleBefore is the pre-apply local visible-hostile count
/// from visibleHostileCount() below (the toggle-3 basis). No-op with nothing
/// pending, outside an active coop battle, or with every toggle off.
void onEvAppliedCancelCheck(const Json::Value& ev, int visibleBefore);

/// CLIENT: the toggle-3 basis - how many distinct HOSTILE units are
/// currently visible to units this machine's seat commands. Purely local FOV
/// state (machine-local, presentation only: a local-FOV visibility-gain
/// check on apply); never hashed, never
/// on the wire. Returns 0 with no live battle.
int visibleHostileCount();

/// CLIENT: the user-facing CANCEL CONTROL (right-click / ESC clears).
/// Returns true iff a pending intent existed and was dropped -
/// the two thin vanilla hook sites use that to CONSUME the input
/// (BattlescapeGame::secondaryAction's client branch, so a right-click
/// clears the held order instead of issuing a second one; and
/// BattlescapeState::handle's SDLK_ESCAPE arm). Clears the banner via
/// CoopBattleUi::clearPending(). False (and completely inert) outside an
/// active coop battle or with nothing pending, so both call sites stay a
/// single guarded call.
bool cancelPendingIntent();

/// Test/introspection (TestServer battle_state): the held plan as
/// {kind, actorId, iseq} - iseq being the iseq of the intent whose busy deny
/// created it - or Json::Value() (null) when nothing is pending.
Json::Value pendingIntent();

// ----- order feedback -----

/// MACHINE-RELATIVE: the co-op SEAT that owns the action currently occupying
/// the HOST's single execution slot, or -1 when nothing is running / this
/// machine cannot attribute it. The seat-attributed
/// STR_COOP_WAIT_FOR_PLAYER_ACTION driver reads it.
///
/// HOST arm: the busy predicate - `BattlescapeGame::isBusy()` OR an open
/// action context (`currentActionId() != 0`). The owner is LATCHED once per busy window,
/// donor semantics (`cbff7951d:BattlescapeState.cpp:5310-5327`): consequence
/// states (death/fall/explosion) are pushed to the FRONT of the queue mid-chain,
/// so re-deriving the owner every tick would mis-attribute a kill to the victim's
/// side. Resolved from `BattlescapeGame::getPrimaryBusyActor()` (the donor call
/// site) and, when the chain has already unwound but its
/// action context is still open, from the arbiter's own pending-chain actor.
///
/// CLIENT arm: a thin client pushes NO BStates (BattlePump.h: "appliers set flags
/// only"), so `isBusy()` is always false there and the donor predicate cannot be
/// used as-is. The client's equivalent knowledge is its own intent bookkeeping:
/// its OWN admitted-and-unfinished action (a bt_ack recorded, its bt_action_end
/// not yet applied) means the blocker is ITSELF; otherwise, while a busy-denied
/// intent is held, the blocker is the only OTHER seat there can be. The
/// other-seat branch is deliberately gated on `seatCount() == 2` - the same
/// 2-player bridge the donor's own name fallback carries, and for the same
/// reason: there is no wire field that names a busy owner, so with 3+ seats this
/// returns -1 and the presenter falls back to the generic busy row rather
/// than guessing. NO new wire field is added for this.
/// Before that
/// bridge, in a co-op battle with parallel turns (never PvP, never the baton mode), the oldest open action of
/// ANOTHER seat that this client is applying - from its first non-consequence ev to its bt_action_end - names
/// the seat that commands its unit (the HOST arm's rule); a unit no seat commands names nobody.
int busyOwnerSeat();

/// CLIENT: is a busy-denied intent currently HELD in the pending slot? Read by
/// the wait-banner driver (a client also waits while ANOTHER seat's action runs,
/// busyOwnerSeat()).
bool hasPendingIntent();

/// CLIENT: the intent round-trip TIMEOUT tick. ONE
/// unconditional guarded call from the pump point (CoopBattleUi::tick()).
/// Fires `Options::coopIntentTimeoutSeconds` after the in-flight intent was sent
/// (default 10 s; <= 0 disables): raises STR_COOP_ACTION_TIMEOUT and RELEASES the
/// one-slot input lock, which is the bug it exists to fix - before this, a
/// lost intent locked its unit for the rest of the battle.
///
/// The timed-out iseq is remembered for the rest of the battle and a late
/// `bt_ack` / `bt_deny` carrying it is PERMANENTLY IGNORED: it
/// updates no lastDeny, raises no banner and re-locks nothing - it only bumps
/// lateAnswersIgnored() below so a test can prove the message ARRIVED and was
/// ignored rather than never came. A late `bt_action_end` still APPLIES
/// untouched: it is host truth and carries state, and nothing here is on the
/// apply path at all.
void tickIntentTimeout();

/// Test/introspection (TestServer event_state / battle_state): this CLIENT's
/// in-flight intent as {iseq, kind, actorId, actionId, ageMs}, or null when the
/// slot is empty. `actionId` is 0 until the host's bt_ack lands. The slot being
/// null after a timeout is the observable proof the input lock was released.
Json::Value inFlightIntent();

/// Test/introspection: how many intents have TIMED OUT on this machine this
/// battle, and the iseq of the most recent one (0 = none yet).
std::uint32_t intentTimeouts();
std::uint32_t lastTimedOutIseq();

/// Test/introspection: how many late bt_ack / bt_deny messages were ignored
/// because their iseq had already timed out. Makes the rule "a late ack/deny
/// changes nothing" a DELIVERED-then-ignored assertion instead of an absence.
std::uint32_t lateAnswersIgnored();

/// Test/introspection (TestServer event_state), battle-scoped.
///   intentsSent()      CLIENT: {kind: count} of the intents this machine sent.
///   intentsReceived()  HOST:   {kind: {admitted, denied}} of the intents it answered.
///   lastActionHalt()   BOTH:   the last non-walk bt_action_end this machine
///                              emitted (host) or applied (client), as
///                              {actionId, halted, reason, continue}; null before
///                              the first. `continue` is the end's own field,
///                              null when absent.
///   lastAftermath()    CLIENT: the last own-action aftermath this machine ran,
///                              as {actionId, kind, continue}; null before the first.
Json::Value intentsSent();
Json::Value intentsReceived();
Json::Value lastActionHalt();
Json::Value lastAftermath();
/// HOST test introspection, battle-scoped.
/// The last 16 bt_intent envelopes onIntent() took into its checks (after the
/// defer_intents hold), oldest first, as {iseq, kind, actorId, skill}; `skill` is
/// the envelope's own field verbatim (null when absent). Nothing reads it.
Json::Value intentsReceivedLog();
/// test/introspection (TestServer event_state), battle-scoped (reset by
/// resetBattleAuthority()).
///   invLocalWrites()  CLIENT: the Inventory moveItem calls the backstop refused.
///   invLastWarning()  BOTH:   the last text the co-op layer put on the inventory's
///                             own message line ("" before the first).
///   invGuard()        BOTH:   the inventory execution-point guard's decisions,
///                             {counts {sent, inflight, baton, interim,
///                             vanilla_refused, host_vanilla}, last {site, op,
///                             decision, itemId, actorId}}; `last` null before the first.
int invLocalWrites();
std::string invLastWarning();
Json::Value invGuard();
/// test/introspection (TestServer event_state `renames`), battle-scoped: zeroed and reset
/// with the other inventory probes by CoopDelta::inventoryProbesReset().
///   renamesProbe()  {sent (CLIENT: rename orders sent), applied, refused (HOST), lastRefusal
///                   (HOST: the last refusal; null before the first)}.
Json::Value renamesProbe();

// TEST-ONLY: delete once real-network
// latency/loss can be injected another way.
/// HOST: hold the next @a count incoming bt_intent messages for @a ms
/// milliseconds before dispatching them normally. This is the only way to make
/// the intent timeout deterministic: it produces a real UNANSWERED intent (the
/// client times out), and then a real LATE answer on the wire (the host's ack or
/// deny, arriving after the client gave up) so the ignore rule is testable too.
/// @a ms 0 disarms.
void requestDeferIntents(std::uint32_t ms, int count);

// TEST-ONLY: the release half of requestDeferIntents() - ONE
// unconditional guarded call at the pump point (the one
// CoopReveal::flushQuiescent() also uses). Inert with nothing deferred.
void releaseDeferredIntentsIfExpired();

} // namespace CoopArbiter

/// the free-function forwarder the vanilla BattlescapeGame::popState
/// thin hook calls (kept outside namespace CoopArbiter so the vanilla call
/// site needs no extra namespace qualification beyond OpenXcom's own).
/// Forwards to CoopArbiter::onChainQuiesced(). Guarded internally (the .cpp
/// body no-ops outside an active coop battle) so the vanilla call site stays
/// a single unconditional call.
void coopOnChainQuiesced();

/// The
/// pre-battle equip phase is open on THIS machine (a co-op session, battle phase not Idle, the equip phase Open). Keyed
/// on the equip phase, never on isCoopBattle(): the host can close its briefing in phase Handshake. False in single
/// player and in every battle without an equip phase. Body: connectionTCP.cpp (g_equip).
bool coopEquipOpen();

/// THIS machine's seat's pre-battle ready flag; false with no seat or no equip phase.
bool coopEquipLocalReady();

/// TEST-ONLY `hold_battle_ready`, CLIENT.
/// Armed, the client's handshake stashes its battle_ready instead of sending it; the TestServer lever's release
/// takes the stash (coopTestHoldBattleReadyTake) and sends it. Inert unless armed. Never called by game logic.
void coopTestHoldBattleReadyArm(bool on);
bool coopTestHoldBattleReadyArmed();
bool coopTestHoldBattleReadyHeld();
bool coopTestHoldBattleReadyTake(Json::Value& out);

/// TEST-ONLY `hold_blob_ack`, CLIENT. Armed, the client withholds its
/// per-chunk WAIT_MAP_SENDER ack while a battle-handshake blob is awaited, so the host's streamer waits.
/// Arm(false) disarms it and returns the count of withheld acks it cleared (the TestServer lever then sends ONE ack).
/// Inert unless armed. Never called by game logic.
int coopTestHoldBlobAckArm(bool on);
bool coopTestHoldBlobAckArmed();
int coopTestHoldBlobAckHeld();

/// coop: TEST-ONLY `hold_save_reply`, HOST. Armed, the host keeps its
/// SEND_FILE_HOST_SAVE_PROGRESS go-ahead; Arm(false) disarms it and returns whether one was held (the TestServer lever then sends it).
/// Inert unless armed. Never called by game logic.
bool coopTestHoldSaveReplyArm(bool on);
bool coopTestHoldSaveReplyArmed();
bool coopTestHoldSaveReplyHeld();

/// coop: TEST-ONLY `hold_blob_ack` scope: 0 "blob", 1 "base"
/// (also while a CoopState 50 is on this machine's stack), 2 "save" (also while the host's save waits for the partner's world). Set by the
/// TestServer lever only. Never called by game logic.
/// coop: scope 3 "upload" (on the host, every world chunk while armed).
void coopTestHoldBlobAckSetScope(int scope);
int coopTestHoldBlobAckScope();

/// coop: TEST-ONLY `hold_battle_accept`, CLIENT. Armed, onOffer stashes its battle_accept; the TestServer lever's release takes
/// the stash (coopTestHoldBattleAcceptTake) and sends it. Inert unless armed. Never called by game logic.
void coopTestHoldBattleAcceptArm(bool on);
bool coopTestHoldBattleAcceptArmed();
bool coopTestHoldBattleAcceptHeld();
bool coopTestHoldBattleAcceptTake(Json::Value& out);

/// coop (TEST-ONLY `throw_next_rx`, either machine, main thread): marks the next message the receive loop handles (of
/// `state`, "" = any; `backHidden`: only under a back-hidden co-op dialog); it throws on every attempt. Never called by game logic.
void coopTestThrowNextRxArm(const std::string& state, bool backHidden);

/// coop (TEST-ONLY `equip_holds_defer`, HOST): while on, the host's
/// pre-battle hold table waits (its newest refusal kept); off sends it at the next pump pass. Never called by game logic.
void coopTestEquipHoldsDefer(bool on);
bool coopTestEquipHoldsDeferred();

/// coop (TEST-ONLY `force_send_failure`, HOST): arms a one-shot - the host's TCP thread takes its real
/// send-failure branch at its next send to the partner (onConnect -3, the partner's socket closed). Inert unless armed.
/// Never called by game logic.
void coopTestForceSendFailureArm();

/// coop (TEST-ONLY `force_server_error`, HOST): onConnect -3 from the main thread with the partner's socket still open, the
/// state a message handler's exception leaves; updateCoopTask's -3 campaign arm runs at the next pump. Never called by game logic.
void coopTestForceServerError();

/// the ONE guarded statement in InventoryState::btnOkClick, right after its cursor refusal. TRUE (the caller returns)
/// only on the pre-battle equip screen of a co-op battle whose equip phase is open (`!tu && parent && coopEquipOpen()`):
/// OK is then a READY TOGGLE - this seat's ready flag flips (host: the local flag; client: `bt_equip_ready`, the flag
/// set locally at once), the OK graphic shows it with its own pressed surface, and nothing closes. The barrier's
/// one-shot pass-through makes it return false once (vanilla's close and startFirstTurn() run). ESC and the inventory
/// key are OK too. False everywhere else (single player, mid-battle inventories, the base screens).
bool coopEquipReadyPress(BattlescapeButton* btnOk, bool tu, bool parent);

/// the ONE guarded statement in InventoryState::init() - under
/// the same predicate as coopEquipReadyPress(), the OK graphic shows this seat's ready flag (pressed in when ready).
void coopEquipApplyOkLook(BattlescapeButton* btnOk, bool tu, bool parent);

/// coop: the pre-battle equip screen's PREV / NEXT for a PvP
/// alien seat with "X-COM equipment for aliens" on - the first guarded statement of InventoryState::btnPrevClick /
/// btnNextClick. Vanilla's cycle selects units of the active side (turn 0: the player side) and allowButtons() is off
/// the seat's side, so it never reaches the seat's aliens: this cycles THIS seat's own units with an inventory in unit
/// order (@a dir -1 / +1, wrapping) and returns TRUE (the caller re-inits). FALSE (vanilla) everywhere else.
bool coopEquipCycleOwnUnit(SavedBattleGame* save, int dir);

/// coop: TRUE when @a u is
/// a PARTNER's soldier on the pre-battle equip screen - the equip phase is open, this seat is on the player side, and @a u is
/// a live player-side unit with an inventory that this seat does not command and another player-side seat does. The screen
/// shows it READ-ONLY (the release line's view): every inventory click, tool and rename on it does nothing. FALSE everywhere
/// else (single player, mid-battle inventories, own units, PvP opponents). Also TRUE for a
/// partner's soldier on a SHARED base inventory screen (see coopBaseInvScreen()); the same gates make it read-only there.
bool coopEquipPartnerView(const BattleUnit* u);

/// coop: InventoryState's constructor registers a base
/// screen (@a game non-null; kept only in a SHARED campaign) and its destructor forgets it (@a game null). While one is registered,
/// coopEquipPartnerView() is TRUE for every soldier on it that this seat does not own (SharedEcon::ownsSoldier()). @a screen is an
/// identity key, never dereferenced.
void coopBaseInvScreen(const void* screen, Game* game);

class Base;
/// coop: InventoryState's constructor
/// registers a base screen and its pile (@a base, @a noCraft: the Soldiers inventory, else the crew's craft) for the co-op partner's
/// pointer (@a game non-null; kept only in a co-op campaign whose base screens show it); its destructor forgets it (@a game null).
/// While registered and the top state, the pump sends this machine's pointer and draws the partner's when both are on the same pile.
/// @a screen is an identity key, never dereferenced.
void coopBasePresenceScreen(const void* screen, Game* game, const Base* base, bool noCraft);

/// coop (TEST-ONLY `base_held_defer`, either machine): while on, this
/// machine keeps its current mapping of the partner's held item on a base screen; off maps it at the next pump pass. Never called by
/// game logic.
void coopTestBaseHeldDefer(bool on);
bool coopTestBaseHeldDeferred();

/// coop: the pre-battle screen's PREV / NEXT for a player-side seat - the second guarded statement of
/// InventoryState::btnPrevClick / btnNextClick, after coopEquipCycleOwnUnit(). Runs vanilla's own
/// BattlescapeState::selectPrevious / NextPlayerUnit with the partner's soldiers admitted (the release line's cycle: every
/// player-side soldier with an inventory, in unit order) and returns TRUE (the caller re-inits). FALSE (vanilla) elsewhere.
bool coopEquipCycleView(BattlescapeState* parent, bool tu, int dir);

/// coop: the ONE guarded statement in InventoryState::init() after coopEquipApplyOkLook(). On the pre-battle screen a
/// partner's soldier hides UNLOAD, copy and paste and shows "Owner: <name>"; an own soldier shows the buttons and hides the
/// line. A no-op everywhere else.
void coopEquipApplyViewLook(Game* game, const BattleUnit* unit, bool tu, bool parent, Surface* unload,
	Surface* createTemplate, Surface* applyTemplate, Text* ownerLine);

/// the equip phase's pump step, ONE unconditional call at
/// the pump point right after CoopHandshake::selectOwnUnitAtEntry(). In order: the host's screen record, the
/// equip-open announce, the barrier; the client's entry, its open and end steps; the waiting line (both). Inert
/// in single player and in every battle without an equip phase.
void coopEquipPump(Game* game);

class State;
/// coop: ~InventoryState's first statement - the co-op
/// partner pointer's overlay (two surfaces the pump added to that screen) is forgotten before the screen deletes its surfaces.
/// A no-op for any other state and in single player.
void coopEquipPresenceDetach(const State* st);

/// coop: TRUE when @a item is in the pre-battle HOLD
/// of a seat other than @a seat - an item on a co-op player's equip cursor is reserved: it is off every other screen's pile
/// (Inventory::arrangeGround() parks it), the host refuses another seat's order for it and no bulk tool takes it. Only while
/// the equip phase is open with a same-side partner (never PvP, never in battle, never single player). Main thread.
bool coopEquipHeldByOtherSeat(const BattleItem* item, int seat);

/// coop: coopEquipHeldByOtherSeat() for THIS machine's seat (Inventory::arrangeGround()'s skip).
bool coopEquipHeldByOther(const BattleItem* item);

/// The covered-battle driver, called by Game::run() once per frame right after the top state's
/// think. HOST only, in an active co-op battle: while another screen covers the BattlescapeState and the base
/// action context is a partner's order (`intent`) or an end of turn (`endturn`), the battle's own timer takes
/// one step, so the partner's action and everything it causes keep running under the host's screens; the AI,
/// falls and the host's own actions still wait. A no-op everywhere else (single player included).
void coopThinkCoveredBattle(Game* game);

/// TEST-ONLY - the fatal-wounds vote's probe record (TestServer event_state
/// `fatalVote`, both machines). Session-lifetime and zero-valued until the vote writes it; cleared only by
/// initBattleAuthority(). Never read by game logic, never on the wire. Body: connectionTCP.cpp.
Json::Value coopFatalVoteProbe();

/// The ONE guarded call at vanilla's fatal-wounds question in
/// BattlescapeGame::requestEndTurn(true). FALSE in single player (vanilla pushes its question). TRUE in a co-op
/// battle, which then pushes nothing: the HOST arms the vote (opened at quiescence by the pump) unless
/// @a endTurnRequested (an end-of-turn kill: either answer ends the battle); a client never gets here.
bool coopFatalVoteArm(SavedBattleGame* save, int wounded, bool endTurnRequested);

/// ConfirmEndMissionState's OK (@a yes) and CANCEL / Esc / abort key, after its own
/// popState. FALSE in single player. A CLIENT voter sends its answer to the host (TRUE). The HOST records its own
/// answer: all voters yes closes the vote `end` and returns FALSE (vanilla's OK then ends the mission); a no closes
/// it `continue` (TRUE); answers still pending push CoopFatalVoteHold (TRUE).
bool coopFatalVoteAnswer(Game* game, bool yes);

/// HOST - TRUE while the fatal-wounds vote is armed or open (onIntent's busy term, the END
/// TURN commit). @a held ("intent" / "commit") is counted in the probe's heldIntents / heldCommits; nullptr asks.
bool coopFatalVoteHolds(const char* held = nullptr);

/// HOST - -1 unless the vote is open; else the lowest partner voter seat still
/// deciding (busyOwnerSeat names it), or 0 when none is (the covered driver stands still on >= 0).
int coopFatalVoteOpen();

/// TEST-ONLY - the abort vote's
/// probe record (TestServer event_state `abortVote`, both machines). Session-lifetime and zero-valued until the vote
/// writes it; cleared only by initBattleAuthority(). Never read by game logic, never on the wire. Body: connectionTCP.cpp.
Json::Value coopAbortVoteProbe();

/// AbortMissionState's unit count. A co-op CLIENT
/// counts through the read-only donor (its dialog is display-only: no tallyUnits(); the probe's dialogDonor); every
/// other machine runs vanilla's tallyUnits(). Body: connectionTCP.cpp.
BattlescapeTally coopAbortDialogTally(SavedBattleGame* save);

/// AbortMissionState's OK, after its own popState. FALSE in
/// single player, outside a co-op battle and in a preview (vanilla aborts). TRUE in a co-op battle: this machine asks
/// the unanimous abort vote (#87's vote, action "abandon_mission") and aborts nothing itself; the host's pump applies a
/// passed vote at quiescence (vanilla's setAborted + finishBattle).
bool coopAbortVoteRequest(Game* game, SavedBattleGame* save);

/// HOST - TRUE while an abort vote is armed, open, passed, or failed with the host's
/// vote screen still on top (the END TURN commit waits). @a held "commit" is counted in the probe's heldCommits;
/// nullptr asks.
bool coopAbortVoteHolds(const char* held = nullptr);

/// The
/// THIN completion/abort hook UnitTurnBState::think() calls, once, at
/// whichever branch actually pops its own state - never per 45-degree tick
/// (the intermediate think() calls that keep turning take neither exit
/// branch). Builds and sends bt_ev{kind:"turn"} (always carrying
/// h:{unitsStats}) from @a unit's CURRENT (post-turn) direction/turret-
/// direction/TU plus the "before" values CoopArbiter captured when this
/// chain began - either onIntent()'s turn branch (an admitted remote intent)
/// or beginHostLocalTurn() above (the host's own local click). No-op outside
/// an active coop battle, or if @a unit is not the actor CoopArbiter is
/// currently tracking a turn chain for (a foreign/AI/SP turn is never coop's
/// to report - kept outside namespace CoopArbiter for the same
/// call-site-simplicity reason as coopOnChainQuiesced()). @a aborted is
/// accepted for a diagnostic log line only: a coop-admitted turn's abort
/// branches are not expected to fire - if one ever does anyway,
/// this still reports the actor's true post-abort state rather than
/// silently dropping the ev.
void coopOnUnitTurnFinished(BattleUnit* unit, bool aborted);

/// The arbiter wraps BattlescapeGame::kneel(bu) directly: admit -> push
/// context -> call -> emit bt_ev kneel + bt_action_end -> pop context. This
/// is the THIN hook BattlescapeGame::kneel() calls at BOTH of its own return
/// points (the successful branch, right before its own `return true`, and the
/// shared `return false` exit) - ONE shared completion point, so it fires
/// identically for BOTH origins: an admitted remote intent (onIntent()'s "kneel"
/// branch, which pushes {actionId,"intent"} + records @a unit as the
/// pending chain actor BEFORE calling kneel()) and the host's own local
/// click (beginHostLocalKneel() above, called from the
/// BattlescapeState::btnKneelClick intercept). No-op outside an active coop
/// battle, or if @a unit is not the actor CoopArbiter is currently tracking
/// a kneel for (a foreign/AI/SP kneel is never coop's to report - kept
/// outside namespace CoopArbiter for the same call-site-simplicity reason
/// as coopOnChainQuiesced()/coopOnUnitTurnFinished()).
///
/// @a succeeded is kneel()'s own return value. validateKneel()'s own doc
/// comment (connectionTCP.cpp) names a deliberate gap: it does not
/// replicate vanilla kneel()'s TU-RESERVATION half of its precondition
/// (`(!isKneeled && getKneelReserved()) || checkReservedTU(...)`), so an
/// admitted intent can rarely still fail here even though this code
/// otherwise treats validateKneel() as authoritative. When @a succeeded is
/// false this still emits a `halted:true` bt_action_end (no ev - nothing
/// changed) and still pops the action context, so the initiating client's
/// in-flight lock resolves instead of leaving the whole battle permanently
/// "busy" (the pushed context must be popped exactly once regardless of
/// which branch kneel() took).
void coopOnKneelFinished(BattleUnit* unit, bool succeeded);

// ===== The walk thin hooks. Kept outside namespace
// CoopArbiter for the same call-site-simplicity reason as
// coopOnChainQuiesced()/coopOnUnitTurnFinished()/coopOnKneelFinished() above.
// Each hook in src/Battlescape/UnitWalkBState.cpp is a single guarded call.
// =============================================================================

/// THIN HOOK 1/3 - UnitWalkBState::think()'s STEP-COMPLETION point (the
/// `if (_unit->getStatus() == STATUS_STANDING)` block right after
/// BattleUnit::keepWalking() advanced the phase). Fires ONCE per COMPLETED
/// step, for BOTH origins ("step evs are origin-independent - a
/// host-origin walk emits them too").
///
/// Three jobs, all self-guarded and inert outside an active co-op battle on
/// the host sim:
///   1. author the ACTING unit's own tile FOV. In a co-op battle
///      the `updateSoldierInfo()` two lines below no longer recalculates tiles
///      (a selection change must not author shared fog), and the acting unit of
///      an ADMITTED REMOTE walk is not the host's selected unit anyway - so
///      without this the host's fog would only catch up at postPathProcedures'
///      end-of-walk calculateFOV, one chunk instead of one step at a time.
///   2. emit `bt_ev walk_step` (a frozen SINGULAR kind) carrying
///      {unit, stepIndex, from, dir, to, tuAfter, enAfter} + h:{unitsStats}.
///      Reveal deltas ride the envelope automatically at the
///      CoopEmit::sendEv choke, which is why job 1 runs first.
///   3. consume the TEST-ONLY requestHaltWalk() latch.
///
/// @return TRUE only when that latch was armed, i.e. "stop this walk at this
/// step boundary" - the vanilla call site turns that into its own
/// `return cancelCurentMove();`, the same exit every real halt takes. FALSE in
/// single player, off the host sim, and in every ordinary step.
bool coopOnWalkStepFinished(BattleUnit* unit, bool sneak = false); // coop: @a sneak = the walk's own sneak, it rides the step ev

/// TEST-ONLY walk-sound probe. coopNoteWalkSound()
/// records one walk-sound decision THIS machine made for @a walker - a step sound past vanilla's own visibility / screen
/// gate (@a startVoice false) or a "start moving" voice (true), played or @a silenced; coopWalkSoundProbe() is
/// TestServer's event_state `walkSounds` {walker id: {steps, stepsSilenced, voices, voicesSilenced}}, cleared by
/// initBattleAuthority(). No-op outside an active co-op battle. Never read by game logic.
void coopNoteWalkSound(const BattleUnit* walker, bool startVoice, bool silenced);
Json::Value coopWalkSoundProbe();

/// The "Enable Other Player Footstep Sounds" option: a walk sound THIS machine is about to play for @a walker - a step
/// sound (@a startVoice
/// false; UnitWalkBState::playMovementSound() past vanilla's gate, the client's walk ghost) or the "start moving" voice
/// (true; the host for a partner's admitted walk, the client's ghost at a walk's first step). TRUE (silenced) when
/// another human seat commands the walker (the co-op partner, the PvP opponent) and the session's option is off (the
/// host's value; the join handshake gives it to the client) or the walk is a PvP (gamemode 2 / 3) sneak (@a sneak); a
/// "start moving" voice is also silenced for a unit no seat commands (vanilla plays it only for the ordering player).
/// This machine's own units and every unit no seat commands keep their step sounds. Records the decision
/// (coopNoteWalkSound()). FALSE outside an active co-op battle (single player byte-identical).
bool coopWalkSoundSilenced(const BattleUnit* walker, bool sneak, bool startVoice);

/// THIN HOOK 2/3 - the head of UnitWalkBState::think()'s own `cancelCurentMove`
/// lambda, i.e. THE cancel path every mid-walk abort funnels through. Latches
/// the halt `reason` for the walk chain currently in flight; the first
/// reason recorded for a chain wins, so a more specific hook (3/3 below, and
/// the spot halt) can record ahead of this catch-all.
///
/// @a vanillaResult is `_action.result` verbatim - vanilla's OWN classification
/// of the two halts it names: "STR_NOT_ENOUGH_TIME_UNITS" (UnitWalkBState.cpp
/// TU guard) maps to `no_tu`, "STR_NOT_ENOUGH_ENERGY" (energy guard) to
/// `no_energy`. An EMPTY result maps to `blocked`, which is exact for the two
/// causes a door-free, contact-free walk can produce
/// (INVALID_MOVE_COST and the `unitInMyWay` occupancy branch) and is the
/// DOCUMENTED approximation for the others (`spot` / `reaction` record their
/// own reason before they cancel, exactly as hook 3/3 does).
///
/// @a reasonOverride, when non-null, is a halt-reason enum string recorded directly
/// instead of mapping @a vanillaResult. No-op outside an active coop battle or
/// when @a unit is not the actor of the walk chain in flight.
void coopNoteWalkHalt(BattleUnit* unit, const std::string& vanillaResult,
	const char* reasonOverride = nullptr);

/// THIN HOOK 3/3 - UnitWalkBState::think()'s TU-RESERVE branch, i.e. the
/// `_parent->checkReservedTU(_unit, tu, energy) == false` sub-expression that
/// is the sole enforcement point for a TU reserve. This
/// REPLACES that sub-expression with one guarded coop call, because the branch
/// has TWO co-op obligations and neither can be met from beside it:
///
///   * The per-machine reserve: the host does NOT apply ITS OWN reserve to a
///     CLIENT-ORIGIN walk. `tuReserved`/`kneelReserved` are saveBlob-EXCLUDED
///     (SharedEcon.cpp) and therefore machine-local, so the value in force
///     during execution would otherwise be the HOST player's - silently
///     truncating a walk the ordering seat's own reserve had already allowed.
///     The CLIENT enforces its own, per step, in sendClientIntent().
///   * The halt reason: this branch leaves `_action.result` EMPTY, which
///     hook 2/3's catch-all would map to `blocked`. A reserve refusal is a TU
///     shortfall, so it records `no_tu` before cancelling.
///
/// @return TRUE when the walk must stop at this step (the vanilla call site
/// turns that into its own `return cancelCurentMove();`). OUTSIDE a co-op
/// battle, and for a HOST-ORIGIN walk inside one, it is exactly
/// `!bg->checkReservedTU(unit, tu, energy)` - the vanilla predicate, called
/// with the vanilla arguments, warning surface included - so single player is
/// byte-identical.
bool coopWalkReserveRefuses(BattlescapeGame* bg, BattleUnit* unit, int tu, int energy);

// =============================================================================
// The spotting halt as a FIRST-CLASS EV (`ev spot`). One more thin hook
// in src/Battlescape/UnitWalkBState.cpp, called at BOTH of vanilla's LIVE
// spot-halt sites.
// =============================================================================

/// THIN HOOK - vanilla's `unitSpotted` walk halts in UnitWalkBState::think():
/// the MID-WALK one (`if (unitSpotted) return cancelCurentMove();`, right after
/// the post-step calculateFOV) and the TURNING one (the
/// `if (unitSpotted && !_action.desperate && !_unit->getCharging() && !_falling)`
/// branch at the end of think(), which covers the pre-first-step facing turn and
/// therefore a ZERO-step walk). Called immediately BEFORE each site's
/// `return cancelCurentMove();`.
///
/// Two jobs, in this order:
///   1. LATCH the halt reason `spot` for the walk chain in flight. This is
///      why the hook has to exist at all: both sites leave `_action.result`
///      EMPTY, and coopNoteWalkHalt()'s catch-all maps an empty result to
///      `blocked` - so without this the completion restate would name the wrong
///      cause and the ordering seat would see the wrong banner.
///      coopNoteWalkHalt() is FIRST-REASON-WINS, which leaves room for this.
///   2. EMIT `bt_ev spot` carrying
///      {unit, seen:[uid...], haltStep} + h:{unitsStats}, through the
///      normal CoopEmit::sendEv choke so any pending `reveal` rides the
///      envelope. An interleaved consequence arrives as
///      its OWN ev in-stream and breaks the walk at exactly its own position -
///      so the ev lands AFTER the last `walk_step` and BEFORE the walk's
///      `bt_action_end`, and its position in the seq stream IS the halt point.
///
/// `seen` is the set of unit ids ADDED to the actor's `_unitsSpottedThisTurn`
/// since the walk chain OPENED. It is BOOKKEEPING, never an FOV transfer: the
/// client appends the ids to the same per-unit vector and writes NO
/// visibility state of any kind.
///
/// No-op in single player, in any non-co-op battle, off the host sim, and for a
/// walk this machine holds no chain for (an AI or panic UnitWalkBState). SP is
/// byte-identical.
void coopNoteWalkSpot(BattleUnit* unit);

/// Test/introspection, like the door counters: how many
/// `spot` envelopes this machine SENT and how many it APPLIED. They are what
/// make "both machines agree on the actor's spotted-this-turn set" a DELIVERY
/// proof rather than a coincidence - a client runs its own
/// TileEngine::calculateUnitsInFOV (a client suppresses only its TILE half), so
/// it can reach the same set without any ev ever arriving. Battle-scoped: both
/// reset at teardown with the rest of the walk-chain bookkeeping.
unsigned int coopSpotEvsEmitted();
unsigned int coopSpotEvsApplied();

/// the WALK ARM's own gate in BattlescapeGame::primaryAction, replacing
/// the coopBlockLocalExecution() call there - see BattleAuthority.h for why
/// that gate is split and what each half guards.
///
/// This is the CONFIRM half: ONE guarded call immediately before
/// `statePushBack(new UnitWalkBState(...))`. On a co-op CLIENT it ships the
/// previewed plan as a `bt_intent walk` through CoopArbiter::sendClientIntent()
/// (the one intent-building function) and returns TRUE, so the push never runs and the
/// client mints NOTHING. On the co-op HOST it stamps
/// the walk's action context (beginHostLocalWalk()) and returns FALSE so
/// vanilla executes exactly as before. FALSE in single player.
///
/// The plan is read out of the LIVE Pathfinding the caller has just calculated
/// and previewed, so both machines describe the same route with the same code.
bool coopInterceptWalkConfirm(BattleUnit* actor, Position dest, bool run,
	bool strafe, bool sneak, bool ignoreSpotted, SavedBattleGame* save);

/// The SHOT execution point in BattlescapeGame::primaryAction -
/// ONE guarded call on the line before the `primaryAction.fire` tripwire, i.e.
/// after vanilla's own pre-execution display (target, CT_NONE, cursor hidden,
/// cameraPosition). In order:
///   1. the baton check at the execution point, on BOTH machines
///      (coopRefuseIfNotMayCommand: rendered not_your_go + coopLocalExecBlocked);
///      a refusal restores the cursor vanilla just hid and returns TRUE;
///   2. on the co-op HOST: FALSE - vanilla executes and its own
///      beginHostLocalCombat() stamps the `host` context;
///   3. on a co-op CLIENT: ships the completed vanilla action as a `shoot`
///      bt_intent through sendClientIntent() (the one intent-building function) and returns
///      TRUE whether or not it went out, so vanilla's execution never runs on a
///      thin client (the tripwire below stays the backstop).
/// FALSE in single player and outside an active co-op battle.
///
/// The same call is the THROW execution
/// point (the same primaryAction line: a BA_THROW ships as a `throw` intent)
/// and the LAUNCH execution point - a second guarded call in
/// BattlescapeGame::launchAction() on the line before the `launchAction`
/// tripwire, where a BA_LAUNCH ships as a `shoot` intent with the action
/// "launch" and its waypoints. Steps 1-3 are the same at both sites.
///
/// A third guarded call is the SPRAY
/// execution point - primaryAction's spray-fire block, on the line before the
/// `primaryAction.spray` tripwire, after vanilla's own spread. A spray ships as
/// a `shoot` intent with the action "auto" and `spray` (the shot voxels). Steps
/// 1-3 are the same; whenever it returns TRUE for a spray it also runs vanilla's
/// two post-push lines the early return skips (sprayTargeting off, waypoints
/// cleared).
bool coopInterceptFireConfirm(BattleAction* action, SavedBattleGame* save);

/// The NON-TARGETING execution point - ONE guarded `else if` in
/// BattlescapeGame::handleNonTargetAction() right after its `result` branch.
/// The prime kinds are BA_PRIME with a chosen fuse (`value > -1`, vanilla's own
/// condition) and BA_UNPRIME; every kind not listed here returns FALSE and
/// vanilla's own branches run unchanged. For a prime kind, in order:
///   1. the baton check on BOTH machines (coopRefuseIfNotMayCommand: rendered
///      not_your_go + coopLocalExecBlocked); a refusal returns TRUE;
///   2. on the co-op HOST: FALSE - vanilla's prime / unprime block runs and
///      coopHostPrime() wraps it in a `host` context;
///   3. on a co-op CLIENT: ships the completed vanilla action as a `prime`
///      bt_intent through sendClientIntent() and returns TRUE whether or not it
///      went out, so no fuse, TU or FOV write ever runs on a thin client.
/// FALSE in single player and outside an active co-op battle.
///
/// + BA_HIT, the melee (the stun rod's STUN
/// row; ActionMenuState's own checks already set the target tile and terrain
/// part): steps 1-2 as above (on the host vanilla's BA_HIT branch pushes the
/// MeleeAttackBState), and on a co-op CLIENT it ships as a `melee` bt_intent,
/// after which the client's own _currentAction is set to BA_NONE - no
/// MeleeAttackBState runs there to clear it (vanilla's own reason for the
/// ActionMenuState reset), so no later popup close re-sends the order.
///
/// + BA_USE with a BT_MEDIKIT or BT_SCANNER item -
/// the popup-close AFTERMATH of a medi-kit or scanner use, whose vanilla branch
/// runs updateGameStateAfterScript(). TRUE on a co-op CLIENT (skipped: the
/// host's use ran it; no baton check - nothing is ordered here), FALSE on the
/// host (vanilla runs it for the host's own use).
bool coopInterceptNonTargetAction(BattleAction* action, SavedBattleGame* save);

/// The PSI-FAMILY execution points in
/// BattlescapeGame::primaryAction - ONE guarded call in the mind probe's branch
/// on the line before its spendTU and ONE in the psi amp's branch on the
/// line before its beginHostLocalCombat(), each after vanilla's own target
/// checks; @a targetUnit is the unit vanilla's own selectUnit(pos) returned.
/// The kinds: BA_USE with a BT_MINDPROBE item, and BA_PANIC / BA_MINDCONTROL /
/// BA_USE with a BT_PSIAMP item; every other action returns FALSE. In order:
///   1. the baton check at the execution point, on BOTH machines
///      (coopRefuseIfNotMayCommand: rendered not_your_go + coopLocalExecBlocked);
///      a refusal restores the cursor and returns TRUE;
///   2. on the co-op HOST: FALSE - vanilla executes (the psi attack's
///      beginHostLocalCombat() stamps the `host` context);
///   3. on a co-op CLIENT: ships the completed vanilla action - a `use_item`
///      bt_intent for the probe, a `psi` bt_intent (action "panic" | "mc" |
///      "use") for the amp - through sendClientIntent() and returns TRUE whether
///      or not it went out, so no TU spend, BState or UnitInfoState runs on a
///      thin client until the host's answer (the probe's screen opens at the
///      order's own bt_action_end).
/// FALSE in single player and outside an active co-op battle.
bool coopInterceptPsiConfirm(BattleAction* action, BattleUnit* targetUnit, SavedBattleGame* save);

// ===== The ITEM and HAND execution points. Each is ONE guarded call at
// its vanilla site, self-guarded (FALSE in single player and outside an active
// co-op battle, so SP is byte-identical), and each checks the baton at the
// execution point on BOTH machines first (coopRefuseIfNotMayCommand: rendered
// not_your_go + coopLocalExecBlocked; the menus, the medi-kit screen and the
// hand buttons stay allowed off-turn). On the co-op HOST each returns
// FALSE (vanilla runs; coopHostMedikit() / coopHostScanner() wrap those uses);
// on a co-op CLIENT each ships the completed vanilla press as an intent through
// sendClientIntent() and returns TRUE whether or not it went out, so none of
// spendTU, medikitUse, medikitRemoveIfEmpty, reloadAmmo or a reaction toggle
// ever runs on a thin client. =====

/// The medi-kit buttons (MedikitState's heal / stimulant / painkiller buttons, the line before
/// each spendTU, after vanilla's own quantity check) and the kit row (ActionMenuState's
/// one-click kit row, the line before its spendTU; @a medikitAction and
/// @a bodyPart -1: the kit's own type decides, vanilla's one-click switch).
/// @a medikitAction is a BattleMediKitAction, @a bodyPart a UnitBodyPart.
/// CLIENT: a `medikit` order {item, targetUnit, targetPos, action, bodypart}.
/// A press while this unit's order is in flight or held pending is IGNORED:
/// TRUE, nothing sent. The one-click row's action is
/// set to BA_NONE whenever TRUE comes back (its menu is already closed); the
/// medi-kit screen keeps its action (the screen stays open, its answer
/// refreshes or closes it).
bool coopInterceptMedikitPress(BattleAction* action, BattleUnit* target, int medikitAction, int bodyPart);

/// The scanner (ActionMenuState's BT_SCANNER row, the line before its spendTU):
/// `if (coopInterceptScannerUse(_action)) { _game->popState(); return; }`.
/// CLIENT: a `use_item` order {item} (the item's battle type tells the host it
/// is the scanner); the ScannerState opens on this machine at the order's own
/// bt_action_end. TRUE sets @a action->type = BA_NONE.
bool coopInterceptScannerUse(BattleAction* action);

/// Reload (BattlescapeState::btnReloadClick, the refusal line):
/// `if (coopInterceptReload(_save->getSelectedUnit(), _save, playableUnitSelected())) return;`.
/// FALSE unless @a playable (vanilla's own gate on the next line then does
/// nothing either). CLIENT: a `reload` order {} - vanilla picks the clip on
/// the host.
bool coopInterceptReload(BattleUnit* unit, SavedBattleGame* save, bool playable);

/// The reaction hand (BattlescapeState::btn{Left,Right}HandItemClick's right-click branch,
/// the refusal lines). HOST: after the baton, Control::HandReaction's
/// ownership term (CoopBattleUi::refuseControl, STR_COOP_DENY_NOT_YOUR_UNIT) -
/// otherwise FALSE and vanilla's own toggle runs, unwrapped.
/// CLIENT: a `reaction_hands` order {hand, ctrl} with THIS machine's
/// Game::isCtrlPressed(true).
bool coopInterceptReactionHands(BattleUnit* unit, SavedBattleGame* save, bool rightHand);

/// The
/// SKILL execution point - SkillMenuState::btnActionMenuItemClick(), the line
/// before its TileEngine::skillUse() (after vanilla's own row pick, weapon pick
/// and updateTU()):
/// `if (coopInterceptSkillUse(_action, selectedSkill)) { _game->popState(); return; }`.
/// The baton at the execution point first, on BOTH machines
/// (coopRefuseIfNotMayCommand). HOST: FALSE - vanilla runs the skill. CLIENT: a
/// `skill` order {skill, action, weapon, tuBasis} - the host alone runs the
/// skill's script and the instant-grenade fuse write and answers `continue` on
/// the order's bt_action_end; on `continue: true` this machine enters its own
/// targeting through a coop ActionMenuState continuation running vanilla
/// ActionMenuState::handleAction() , unless the player has moved on.
/// Whenever TRUE comes back @a action is left as vanilla's own
/// stop leaves it (not targeting, BA_NONE, no skill), so the closed menu's
/// handleNonTargetAction() does nothing. FALSE in single player and outside an
/// active co-op battle.
bool coopInterceptSkillUse(BattleAction* action, const RuleSkill* skill);

/// the HOST's OWN skill use as an
/// INSTANT host action - the medi-kit / scanner shape (coopHostMedikit(), coopHostScanner(),
/// CoopDelta.h) for the skill execution point above. ONE call in SkillMenuState::btnActionMenuItemClick(), on
/// the line right AFTER its TileEngine::skillUse() (reached only when the guard above answered FALSE): mint,
/// push {id,"host"}, the `skill` cue {actor, unit (= actor), skill} whose delta carries everything the skill's
/// script changed (tags, TU, stats), then the close through onChainQuiesced() -> closeBaseContext() (its
/// bt_action_end). Coop + hostSim only: a no-op in single player and on a client (whose press is a `skill`
/// order); a logged no-op while another action context is open (the effect then rides that context's next
/// delta, coopHostPrime()'s rule).
void coopHostSkill(BattleAction* action, const RuleSkill* skill);

/// the HOST's OWN Zero TU
/// press as an INSTANT host action - coopHostSkill()'s shape above. ONE call in
/// BattlescapeState::btnZeroTUsClick(), on the line right AFTER its BattleUnit::clearTimeUnits() (the host only:
/// CoopBattleUi::refuseControl(ZeroTu) refuses a client and a unit this seat does not command):
/// mint, push {id,"host"} (context kind `zero_tu`), the `zero_tu` cue {actor, unit (= actor)} whose delta
/// carries the zeroed TU, then the close through onChainQuiesced() -> closeBaseContext(). No partner twin (the
/// second player's press stays refused). Coop + hostSim only; a logged no-op while another context is open.
void coopHostZeroTu(BattleUnit* unit);

/// The medi-kit screen's onEndClick guard (MedikitState::onEndClick, its
/// TileEngine::medikitRemoveIfEmpty() line): TRUE on a co-op CLIENT - the host
/// removes an emptied consumable kit right after the use that emptied it
/// and the removal reaches this machine through the delta, so the
/// client never removes an item itself. FALSE on the host and in single player.
bool coopClientSkipsMedikitRemoval();

/// The halt LATCH - ONE guarded
/// call in BattlescapeGame::popState() before vanilla's player warning. On the
/// co-op HOST, while an `intent` context is the base, a popped state whose
/// actor is that context's actor is a REMOTE action: the first non-empty
/// vanilla `result` of such a state (the base context on top of the stack, not
/// a nested reaction's) is latched for the context - closeBaseContext() ships it
/// as `halted`/`reason` on the context's bt_action_end - and TRUE is returned so
/// vanilla skips BOTH host-screen side effects for it (the warning and the
/// throw/launch cancel of the HOST player's own action). FALSE everywhere else
/// (SP, a client, the host's own actions), so vanilla is byte-identical there.
bool coopLatchActionResult(const BattleAction& action);

// ===== The IN-BATTLE INVENTORY
// execution points. Picking an item up is local (vanilla's own cursor); every
// placement is an `inv_move` intent the host checks and performs. Each guard is
// ONE guarded call at its vanilla site in Inventory.cpp / InventoryState.cpp,
// self-guarded (FALSE / the vanilla value in single player and outside an
// active co-op battle, so SP is byte-identical). Every decision a guard takes
// is recorded on the invGuard probe (CoopArbiter::invGuard()). =====

/// The MOVE execution points (Inventory::mouseClick's drop / ground-stack /
/// cursor-stack blocks, the Ctrl body->ground block, fitItem's Ctrl placement and
/// quickDrop's paperdoll drop), called on the line before vanilla's own
/// `if (!_tu || spendTimeUnits(...))`; @a site names the block ("drop",
/// "stack", "stack_cursor", "ctrl_ground", "ctrl_fit", "paperdoll"). TRUE =
/// vanilla's block must not run. In order:
///   1. !coopMayCommand(unit): TRUE on BOTH machines; when the baton is the
///      failure the rendered not_your_go text goes on the inventory's own
///      message line and coopLocalExecBlocked +1 (decision `baton`);
///   2. the co-op HOST: FALSE, vanilla runs (`host_vanilla`);
///   3. CLIENT: this unit's order in flight or held pending: TRUE, nothing sent
///      (`inflight`);
///   4. (no site is an `interim` one: ctrl_ground, ctrl_fit and paperdoll ship
///      their vanilla-resolved target as a concrete move like every other site;)
///   5. CLIENT, the move costs more TU than the unit has: FALSE - vanilla's own
///      spend fails and warns with no write (`vanilla_refused`);
///   6. CLIENT: an `inv_move {op move}` order is sent and TRUE (`sent`).
bool coopInterceptInvMove(Inventory* inv, BattleUnit* unit, BattleItem* item, const RuleInventory* slot,
	int x, int y, const char* site);

/// The LOAD execution point (mouseClick's put-ammo-in-weapon block, the line
/// before its spendTimeUnits(tuCost)); site `load`, the clip recorded. Steps 1-3
/// above; then CLIENT: @a tuCost more than the
/// unit's TU -> FALSE, vanilla warns (`vanilla_refused`); else an `inv_move {op
/// load, item clip, weapon, swap}` order is sent (swap = the weapon's ammo slot
/// is loaded: vanilla's Shift quick-swap passed) and TRUE (`sent`).
bool coopInterceptInvLoad(Inventory* inv, BattleUnit* unit, BattleItem* clip, BattleItem* weapon, int tuCost);

/// The UNLOAD / UNPRIME execution point (Inventory::unload, the line before its
/// cost.spendTU(); the Shift+click on a hand weapon and the UNLOAD button);
/// site `unload`. Steps 1-3 above; then CLIENT:
/// !cost.haveTU() -> FALSE, vanilla's spendTU(&err) warns (`vanilla_refused`);
/// else an `inv_move {op unload, item}` order is sent and TRUE (`sent`). The
/// caller returns false on TRUE (no sound until the answer).
bool coopInterceptInvUnload(Inventory* inv, BattleUnit* unit, BattleItem* item, BattleActionCost& cost);

/// The PRE-BATTLE FUSE execution points - Inventory::mouseClick's right-click default fuse and
/// unprime (`if (coopInterceptInvFuse(this, _selUnit, item, <value>)) return;`) and PrimeGrenadeState's timer
/// button (the guard before its setFuseTimer(); @a inv and @a unit null: the pre-battle screen's and the item's
/// owner, else that screen's unit); @a fuse = the value vanilla writes (-1 unprimes); site `fuse`. FALSE (vanilla)
/// unless a co-op battle's pre-battle equip phase is open (SP, base screens and the battle stay byte-identical).
/// Then the head (ownership and side - no baton in the equip phase), the held and in-flight rules;
/// the HOST: FALSE, vanilla writes (the head latches); a CLIENT sends one TU-free `inv_move {op fuse, item, fuse}`
/// order and TRUE - it never writes a fuse itself.
bool coopInterceptInvFuse(Inventory* inv, BattleUnit* unit, BattleItem* item, int fuse);

/// the PRE-BATTLE QUICK-UNLOAD execution point, the line
/// before Inventory::unload()'s `if (quickUnload && !_tu)` branch:
/// `if (quickUnload && !_tu && coopInterceptInvQuickUnload(this, _selUnit, _selItem)) return false;`; site
/// `quick_unload`. As coopInterceptInvFuse(): FALSE outside the co-op equip phase and on the host; a CLIENT sends
/// one TU-free `inv_move {op quick_unload, item}` order (the weapon stays, its ammo to the ground) and TRUE.
bool coopInterceptInvQuickUnload(Inventory* inv, BattleUnit* unit, BattleItem* item);

/// the
/// PRE-BATTLE BULK TOOL execution points - the first statement of InventoryState::_applyInventoryTemplate (@a op
/// `apply`, @a layout = the template it applies: the template buttons, the personal and the global layouts) and of
/// onClearInventory / onAutoequip after their cursor checks (`clear` / `autoequip`, @a layout null):
/// `if (coopInterceptInvBulk(_inv, _battleGame->getSelectedUnit(), <op>, <layout>)) return;`. FALSE (vanilla)
/// unless a co-op battle's pre-battle equip phase is open. Then the head (ownership and side), the held and
/// in-flight rules; the HOST: FALSE, vanilla writes (the head latches); a CLIENT sends one tracked
/// `inv_bulk {op, template?}` order and TRUE - it never runs the tool itself.
bool coopInterceptInvBulk(Inventory* inv, BattleUnit* unit, const char* op,
	const std::vector<EquipmentLayoutItem*>* layout);

/// the two layout SAVES, a void note right
/// after vanilla built the layout - btnCreatePersonalTemplateClick (@a op `save_personal`, @a index -1) and
/// saveGlobalLayout (`save_global`, @a index = the slot); vanilla's own local write always runs. A CLIENT in a
/// SHARED campaign's pre-battle equip phase also sends one tracked `inv_bulk {op, template, index?}` order, so the
/// host writes the same layout into the one shared world; a skirmish or SEPARATE save stays on this machine (lost
/// after the battle). A no-op on the host and in single player. The order is QUEUED and sent by the equip pump once no
/// order is in flight or held on this machine (never
/// dropped by the in-flight lock); it carries the layout, its armor half and a save-dialog save's slot name as this
/// machine's vanilla save stored them.
void coopNoteInvLayoutSave(BattleUnit* unit, const char* op, int index, const std::vector<EquipmentLayoutItem*>& layout);

/// mouseClick's right-click RETURN of the cursor item. CLIENT: this
/// unit's `inv_move` for @a item is in flight - TRUE, the item stays on the
/// cursor until the host answers; a HELD `inv_move` for @a item is cancelled
/// (cancelPendingIntent()) and FALSE - vanilla returns the item. FALSE
/// everywhere else.
bool coopInterceptInvReturn(Inventory* inv, BattleItem* item);

/// The client BACKSTOP - the first line of Inventory::moveItem. On a
/// co-op CLIENT every call is refused, counted (invLocalWrites) and logged: no
/// inventory write may run on a thin client. FALSE on the host and in SP.
bool coopInvLocalWriteRefused();

/// coop: THIS machine's motion
/// scanner marked @a unit for @a turn - vanilla's setScannedTurn(), the one ScannerView line it replaces. In a co-op
/// battle a NEW mark (the unit's scanned turn was another) is shared once with the co-op partner - a mapped seat of THIS
/// seat's side; never the PvP opponent - as an untracked `bt_scan_mark {battleId, unit, turn}`. coopOnScanMark() is
/// the receiver (direct battle-lane dispatch): it marks its own copy of the unit for the current turn. The mark is
/// display-only (`_scannedTurn` is never saved, hashed or streamed). Single player: vanilla's setter only.
void coopNoteScannedUnit(BattleUnit* unit, int turn);
void coopOnScanMark(const Json::Value& msg);

/// InventoryState's destructor gravity step. nullptr on a co-op CLIENT
/// (the host runs gravity, light and FOV for the actor's tile inside every
/// `inv_move` context; the client keeps its local light / FOV), @a u
/// everywhere else.
BattleUnit* coopInventoryCloseGravityUnit(BattleUnit* u);

/// the
/// in-battle RENAME execution point, the first statement of InventoryState::edtSoldierChange:
/// `if (coopInterceptRename(_inv->getSelectedUnit(), _txtName->getText())) return;`.
/// FALSE (vanilla) in single player, outside an active co-op battle, with no unit, and for a unit without a
/// geoscape Soldier (vanilla writes nothing then). HOST: the host latch's `rename` site
/// (CoopDelta::noteHostInventoryChange), FALSE - vanilla writes and the latch ships the names. CLIENT: when
/// @a text differs from the last text sent for the unit an untracked `rename {name}` order goes
/// out (renames.sent +1); TRUE either way - the client never writes a name itself.
bool coopInterceptRename(BattleUnit* unit, const std::string& text);

/// coop: the automatic desync repair's probe record,
/// process-lifetime, read by TestServer's `resync_state`: counters desyncs, offered, held, skipped, teardowns, loaded,
/// completed, released, failed, notices; last {bucket, seq, kind, battleId}; lastSkip / lastFail / lastOfferSide; bundle
/// (this machine's last report zip); holdArmed; frozen (this machine's live desyncFrozen). Never read by game logic.
Json::Value coopResyncRecord();
/// coop: TEST-ONLY `resync_hold` lever (HOST). Armed, a desync report is logged with no repair offered. Inert unless
/// armed. Returns the armed state.
bool coopResyncHoldArm(bool on);
/// coop: TEST-ONLY `resync_ready_mismatch` lever (HOST, one-shot): the next automatic repair offer expects a wrong
/// copy hash, so onReady() takes its resumed mismatch branch. Inert unless armed.
void coopTestResyncReadyMismatchArm();

/// "Enable Reaction Fire in PvP". TRUE on the co-op
/// HOST in a PvP battle (gamemode 2 / 3) whose host had the option off when the battle started (initBattleAuthority()
/// takes Options::EnableReactionFirePvp into connectionTCP::_enable_reaction_shoot): UnitWalkBState then skips its
/// walk-step reaction check - the release line's one gated site (main UnitWalkBState.cpp :465). A client's own setting
/// never applies; every other reaction trigger (kneel, shot, melee, fall) stays vanilla. FALSE in single
/// player, on a client, in classic / SHARED / SEPARATE co-op and in PvE2.
bool coopPvpWalkReactionOff();

} // namespace OpenXcom
