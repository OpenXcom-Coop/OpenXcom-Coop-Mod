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

#include "SharedEcon.h"
#include "SeparateEcon.h"
#include "GiftNoticeState.h"
#include "../Mod/RuleVideo.h"
#include "../Menu/CutsceneState.h"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstring>
#include <ctime>
#include <deque>
#include <fstream>
#include <map>
#include <mutex>
#include <set>
#include <unordered_map>
#include <utility>
#include <vector>

#include "../Engine/Game.h"
#include "../Engine/Language.h"
#include "../Engine/LocalizedText.h"
#include "../Engine/Logger.h"
#include "../Engine/Options.h"
#include "../Engine/Screen.h"
#include "../Engine/RNG.h"
#include "../Engine/State.h"
#include "../Engine/Yaml.h"
#include "../Mod/Mod.h"
#include "../Mod/RuleItem.h"
#include "../Mod/RuleCraft.h"
#include "../Mod/RuleSoldier.h"
#include "../Mod/RuleResearch.h"
#include "../Mod/RuleManufacture.h"
#include "../Mod/Unit.h"
#include "../Mod/Armor.h"
#include "../Mod/RuleBaseFacility.h"
#include "../Mod/RuleRegion.h"
#include "../Mod/RuleInterface.h"
#include "../Savegame/SavedGame.h"
#include "../Savegame/GameTime.h"
#include "../Savegame/Base.h"
#include "../Savegame/BaseFacility.h"
#include "../Savegame/Region.h"
#include "../Savegame/Craft.h"
#include "../Savegame/ItemContainer.h"
#include "../Savegame/Transfer.h"
#include "../Savegame/Soldier.h"
#include "../Savegame/RankCount.h" // the manual promotion openings rule
#include "../Savegame/ResearchProject.h"
#include "../Savegame/Production.h"
#include "../Savegame/Ufo.h"
#include "../Savegame/MissionSite.h"
#include "../Savegame/AlienBase.h"
#include "../Savegame/Waypoint.h"
#include "../Savegame/Target.h"
#include "../Savegame/AlienMission.h"
#include "../Savegame/CraftWeapon.h"
#include "../Savegame/Vehicle.h"       // the forced storage sale's craft cleanup
#include "../Engine/Collections.h"     // vanilla's vehicle deleteIf
#include <climits>                     // INT_MAX
#include <cstdlib>                     // std::atoi (selection row keys)
#include "../Savegame/Country.h"
#include "../Savegame/WeightedOptions.h"
#include "../Savegame/SavedBattleGame.h"
#include "../Savegame/EquipmentLayoutItem.h"
#include "../Engine/Collections.h"
#include "../Savegame/BattleItem.h"
#include "../Savegame/BattleUnit.h"
// PRD-I0: the sync-check sweep reads tiles (terrain/fire/smoke), inventory slot
// ids and the TilePart enum directly.
#include "../Savegame/Tile.h"
#include "../Mod/MapData.h"
#include "../Mod/RuleInventory.h"
#include "../Battlescape/BattlescapeGame.h"
#include "../Battlescape/BattlescapeState.h"
#include "../Mod/RuleUfo.h"
#include "../Mod/RuleCraftWeapon.h"
#include "../Mod/RuleCountry.h"
#include "../Mod/RuleAlienMission.h"
#include "../Mod/AlienRace.h"

// The battle hash region needs the four
// battle serializers plus RuleInventory (item slot-type check) and the
// diagnostic-bundle helpers (CrossPlatform file I/O, miniz zip writer -
// already a project dependency via Engine/FileMap.cpp, no new library).
#include "../Savegame/BattleUnit.h"
#include "../Savegame/BattleItem.h"
#include "../Savegame/Tile.h"
#include "../Savegame/SavedBattleGame.h"
#include "../Savegame/Node.h" // the `synced` bucket's node types
#include "../Mod/RuleInventory.h"
#include "../Engine/CrossPlatform.h"
#include "../../libs/miniz/miniz.h"

#include <cmath>
#include "../Basescape/BaseView.h"
#include "../Basescape/SellState.h"
#include "../Basescape/CraftWeaponsState.h" // issue #121: shared craft-weapon capacity gate
#include "../Basescape/SoldierTransformationState.h" // soldier_transform runs vanilla's transformation
#include "../Mod/RuleSoldierTransformation.h"
#include "../Geoscape/GeoscapeState.h"
#include "../Geoscape/DogfightState.h" // the replica's lost-craft guard
#include "../Geoscape/ConfirmLandingState.h"
#include "../Geoscape/Globe.h"
#include "../Geoscape/ResearchCompleteState.h"
#include "../Geoscape/ProductionCompleteState.h"
// Generic SHARED alert replication (see alertApply): every informational geoscape popup
// the host-only sim raises has to be rebuilt on the replica from ids / rule names.
#include "../Geoscape/UfoLostState.h"
#include "../Geoscape/LowFuelState.h"
#include "../Geoscape/CraftErrorState.h"
#include "../Geoscape/DogfightErrorState.h"
#include "../Geoscape/ItemsArrivingState.h"
#include "../Geoscape/ResearchRequiredState.h"
#include "../Geoscape/NewPossibleResearchState.h"
#include "../Geoscape/NewPossibleManufactureState.h"
#include "../Geoscape/NewPossiblePurchaseState.h"
#include "../Geoscape/NewPossibleCraftState.h"
#include "../Geoscape/NewPossibleFacilityState.h"
#include "../Geoscape/TrainingFinishedState.h"
#include "../Geoscape/GeoscapeEventState.h"
#include "../Ufopaedia/Ufopaedia.h" // the replica opens the arc's article
#include "../Battlescape/DebriefingState.h" // geo_event windows wait out the debriefing
#include "../Savegame/ResearchDiary.h"       // geo_event diary entries
#include "../Geoscape/AlienBaseState.h"
#include "../Geoscape/BaseDestroyedState.h"
#include "../Savegame/AlienBase.h"
#include "../Mod/RuleEvent.h"
#include "../Mod/AlienDeployment.h"
#include "../Savegame/GeoscapeEvent.h"
#include "../Menu/ErrorMessageState.h"
#include "../Basescape/SellState.h"     // the SelectionBinder is a friend of the screen
#include "../Basescape/PurchaseState.h" // ... and of the Purchase/Hire screen
#include "../Battlescape/CannotReequipState.h" // the reequip decrement rides the apply
#include <iomanip>                      // Purchase's space-used text, as the screen formats it
#include <sstream>
#include "../Interface/Text.h"          // the binder's totals redraw
#include "../Interface/TextButton.h"
#include "../Engine/Unicode.h"
#include "../Basescape/TransferItemsState.h"          // the binder on Transfer and
#include "../Basescape/ManageAlienContainmentState.h" // Alien Containment (a friend of each screen)
#include "../Interface/TextList.h"                    // the highlight and the one-row-shorter list
#include "../Engine/Font.h"
#include "../Savegame/EquipmentLayoutItem.h"          // the soldiers' gear as transfer item rows
#include "../Savegame/Vehicle.h"
#include "../Battlescape/CannotReequipState.h"

#include "connectionTCP.h"
#include "CoopState.h"
#include "CoopDelta.h" // the battleEnd record's fenceDeferredPasses
#include "../version.h" // coop: the crash report's build fields

namespace OpenXcom
{
// coop: the close of the geoscape windows that hold an object about to be deleted (coopCloseMirrorHolders,
// connectionTCP.cpp); SharedEcon's baseDestroyedApply calls it before it deletes a base and its crafts.
bool coopCloseMirrorHolders(Game* game, const std::vector<Target*>& doomed);

namespace SharedEcon
{

namespace {

// ---- Command registry --------------------------------------------------------
struct Handler { CmdValidator validate; CmdApplier apply; };
std::unordered_map<std::string, Handler>& registry()
{
	static std::unordered_map<std::string, Handler> r;
	return r;
}
bool g_inited = false;

// ---- Deferred main-thread work (mirrors the waitedTrades idiom) --------------
// A command queued for host-side validate+apply+broadcast. `remote` = received
// from a client over the wire (reply with shared_ok/shared_fail); !remote = the
// host's own UI (surface a failure locally, no wire reply).
struct PendingCmd
{
	std::string cmd;
	int seq = 0;
	int seat = 0;
	int baseId = -1;
	int baseKey = 0; // the base's coop id when the sender queued it (resolveBaseRef)
	Json::Value payload;
	bool remote = false;
	bool separateProtocol = false;
};

std::mutex g_mx;                     // guards the four queues below
std::deque<PendingCmd>  g_cmdQ;      // host:      to validate+apply+broadcast
std::deque<Json::Value> g_applyQ;    // replica:   shared_apply to apply
std::deque<std::pair<std::string, int>> g_failQ; // initiator: shared_fail {reason, seq} to surface (seq: the awaited confirm's)
int g_resyncServeQ = 0;              // host:      pending shared_resync_requests
bool g_applyHold = false;            // replica:   g_applyQ held until a streamed world's adoption

// Per-machine monotonic command sequence stamp (protocol `seq`).
std::atomic<int> g_seqCounter{0};

// ---- Diagnostics (harness-observable) ----------------------------------------
std::atomic<uint64_t> g_cmdN{0};     // shared_cmd this host validated
std::atomic<uint64_t> g_okN{0};      // shared_ok sent (host) / received (client)
std::atomic<uint64_t> g_failN{0};    // shared_fail surfaced (initiator) / sent (host)
std::atomic<uint64_t> g_applyN{0};   // shared_apply applied by this machine
std::atomic<uint64_t> g_unknownN{0}; // shared_cmd naming an unregistered cmd
std::mutex g_failMx;
std::string g_lastFail;

// ---- PRD-J10: desync repair bookkeeping --------------------------------------
std::atomic<uint64_t> g_mismatchN{0};  // checksum mismatches seen (replica)
std::atomic<uint64_t> g_resyncReqN{0}; // resyncs asked for (replica) / served (host)
bool g_resyncPending = false;          // replica: a world restream is in flight
bool g_resyncGaveUp = false;           // replica: throttled out, popup already shown
int64_t g_lastResyncGameMin = -1;      // replica: game-minute stamp of the last resync
// Replica: wall-clock ms of the last sign that a world stream is coming - the
// resync request, a restream mark or a stream chunk. The in-flight guard and the
// result hold live while this is recent (RESYNC_PENDING_TIMEOUT_MS), however fast
// the game clock runs.
int64_t g_streamProgressMs = -1;
// Replica: host results held while a resync restream is in flight. Right after it
// snapshots its world for a restream, the host sends a restream mark in the same
// message order as its results: every result before the mark is in that snapshot,
// every result after it is not. Results after the mark wait here until that world
// is adopted, then apply once, to it (holdResultDuringRestream). Main thread only.
int g_restreamMarks = 0;    // marks whose world is not adopted yet
bool g_releaseHeld = false; // adopted: re-dispatch g_heldResults on the next update
std::deque<std::pair<std::string, Json::Value>> g_heldResults;
// The checksum rides the geoscape `time` heartbeat, which the host emits at LINK
// RATE (~2000/s). Log a mismatch ONCE per episode, not once per heartbeat: a
// per-heartbeat log is thousands of fopen/fwrite/fclose per second on the
// replica's main thread, which starves the very world-restream that repairs it -
// the repair then never lands and the desync looks unfixable. (Measured: the
// restream degrades from <1s to >4s per 3KB chunk, then stalls.)
bool g_mismatchLogged = false;
// Wall-clock ms at which the CURRENT mismatch streak started, -1 = in agreement.
// See the debounce in verifyWorldChecksum.
int64_t g_mismatchSinceMs = -1;

bool isHost() { return connectionTCP::getHost(); }

// baseId decision (PRD offered coop_base_id OR index-in-_bases): we use the
// INDEX into SavedGame::getBases(). The SHARED world is a byte-faithful streamed
// replica, so host and every replica hold the same base list in the same order.
// Base add/remove and base_move also ride shared_apply, keeping the
// ordering in lock-step. A command still in flight across a base_move would
// name the wrong base by index alone, so each reference also carries the
// base's _coop_base_id (resolveBaseRef below).
Base* resolveBase(Game* game, int baseId)
{
	if (!game || !game->getSavedGame()) return nullptr;
	auto* bases = game->getSavedGame()->getBases();
	if (baseId < 0 || baseId >= (int)bases->size()) return nullptr;
	return (*bases)[baseId];
}

// A player may move a base in the list (base_move) while a command that names
// a base by its index is still on its way, so every base reference also
// carries that base's _coop_base_id (the host mints it and the world stream and
// base_new carry it, so both machines hold the same id). The index wins while it
// still names the keyed base; otherwise the key finds the base. A key shared by
// two bases resolves to nothing rather than to a guess. A key that no base holds
// falls back to the index (an id that differs between the machines, the old
// behaviour). Key 0 = the sender gave none.
int baseKeyAt(Game* game, int baseId)
{
	Base* base = resolveBase(game, baseId);
	return base ? base->_coop_base_id : 0;
}

Base* resolveBaseRef(Game* game, int baseId, int baseKey)
{
	Base* atIndex = resolveBase(game, baseId);
	if (baseKey == 0 || !game || !game->getSavedGame()
		|| (atIndex && atIndex->_coop_base_id == baseKey)) return atIndex;
	Base* found = nullptr;
	for (Base* base : *game->getSavedGame()->getBases())
	{
		if (base->_coop_base_id != baseKey) continue;
		if (found) return nullptr;
		found = base;
	}
	return found ? found : atIndex;
}

// Base indexes inside a payload (a transfer's destination, a craft's target
// base, a dogfight command's craft base) get the same key, under "<field>Key".
const char* const kPayloadBaseFields[] = { "toBaseId", "tBaseId", "baseId" };

void keyPayloadBaseRefs(Game* game, Json::Value& payload)
{
	if (!payload.isObject()) return;
	for (const char* field : kPayloadBaseFields)
		if (payload.isMember(field))
			payload[std::string(field) + "Key"] = baseKeyAt(game, payload[field].asInt());
}

// Rewrites each keyed payload index to the base's index in THIS machine's list
// and re-keys it, so the appliers keep resolving plain indexes.
void resolvePayloadBaseRefs(Game* game, Json::Value& payload)
{
	if (!payload.isObject()) return;
	for (const char* field : kPayloadBaseFields)
	{
		const std::string key = std::string(field) + "Key";
		if (!payload.isMember(field) || !payload.isMember(key)) continue;
		Base* base = resolveBaseRef(game, payload[field].asInt(), payload[key].asInt());
		payload[field] = base ? baseIndex(game, base) : -1;
		payload[key] = base ? base->_coop_base_id : 0;
	}
}

void setLastFail(const std::string& reason)
{
	std::lock_guard<std::mutex> lk(g_failMx);
	g_lastFail = reason;
}

// ---- the initiator's awaited confirms, by screen key ----------
// A screen opened through the real UI registers its submitted seq (keepAfterSubmit); the answer is recorded here -
// shared_ok on receipt, shared_fail when update() surfaces it, the host's own command at its apply / rejection - and
// the screen's think() takes it. A seq nobody awaits (a harness test command, a forced screen, a cancelled one) is ignored.
std::mutex g_resMx;
std::map<int, std::string> g_awaitBySeq;  // awaited seq -> screen key
std::map<std::string, int> g_awaitByKey;  // screen key -> awaited seq
std::map<std::string, int> g_resultByKey; // screen key -> 1 ok / -1 failed, until taken

// ---- the shared selection store, by screen key ----------------------
// The host's entry is the truth; a replica's is a mirror written only by the sel_* broadcasts and the confirm appliers
// (selConsume). Main thread only. Row keys: i:<itemType>, s:<soldierId>, c:<craftId>:<craftType>, sci, eng.
struct SharedSel
{
	std::map<std::string, int> rows, editors, eseqs;
	uint32_t rev = 0;
	std::set<int> viewers;
	bool consumed = false;
	uint32_t consumedRev = 0;
	uint64_t consumedHash = 0;
};
std::map<std::string, SharedSel> g_sel;
// This machine's bookkeeping beside the store (never on the wire), per key: per row the highest eseq of its own edits
// seen in the list (a consume clears the list's eseqs, not this) and how many of its sel_open were answered.
struct SelLocal { std::map<std::string, int> ownSeen; int openEchoes = 0; };
std::map<std::string, SelLocal> g_selLocal;
std::map<std::string, std::pair<bool, int>> g_selCarry; // carried-over key -> the old binder's {acked, open echo wanted}
int g_selEseq = 0;                                      // this machine's edit sequence (sel_set eseq)
std::string g_selConfirmKey;                            // host: the stamped confirm being applied (selConfirmRules -> selConsume)
uint64_t g_selConfirmHash = 0;                          // host: the hash of the rows that confirm applies
void selConsume(Json::Value& payload);                  // with the sel_* appliers below

void recordResult(int seq, int result)
{
	std::string key;
	{
		std::lock_guard<std::mutex> lk(g_resMx);
		auto it = g_awaitBySeq.find(seq);
		if (it == g_awaitBySeq.end()) return;
		key = it->second;
		g_awaitBySeq.erase(it);
		auto k = g_awaitByKey.find(key);
		if (k != g_awaitByKey.end() && k->second == seq) g_awaitByKey.erase(k);
		g_resultByKey[key] = result;
	}
	Log(LOG_INFO) << "[SHARED] confirm answered: " << key << " seq=" << seq << (result > 0 ? " ok" : " failed");
}

// A forced screen's "solved" - vanilla's own over-the-limit gates (SellState :92 / :1362,
// ManageAlienContainmentState :299-302).
bool storageSolved(Base* base)
{
	return !(Options::storageLimitsEnforced && base->storesOverfull());
}

bool containmentSolved(Base* base, int prisonType)
{
	const int availableContainment = base->getAvailableContainment(prisonType);
	const int freeContainment = availableContainment - base->getUsedContainment(prisonType);
	return !((availableContainment == 0 || Options::storageLimitsEnforced) && freeContainment < 0);
}

// What a forced storage SellState lists for @a rule (SellState :257-275 at the post-battle
// origin): base stock + item transfers + transfer crafts' and base crafts' items (their weapons and vehicles too when
// the stores are critically over).
int forcedSellAvailable(Base* base, const RuleItem* rule, bool critical)
{
	int qty = base->getStorageItems()->getItem(rule);
	for (auto* transfer : *base->getTransfers())
	{
		if (transfer->getItems() == rule)
			qty += transfer->getQuantity();
		else if (transfer->getCraft())
			qty += critical ? transfer->getCraft()->getTotalItemCount(rule) : transfer->getCraft()->getItems()->getItem(rule);
	}
	for (auto* craft : *base->getCrafts())
		qty += critical ? craft->getTotalItemCount(rule) : craft->getItems()->getItem(rule);
	return qty;
}

// SellState::btnOkClick's own removal of one sold item (:739-946, ported verbatim): the base stock, then
// each base craft's item container and then its weapons / vehicles (the launcher / clip remainders go to the stores),
// then the transfers in list order (an item transfer shrinks or goes; a transfer craft is cleaned like a base craft).
// Host and replica run it on identical worlds.
void forcedSellRemove(Base* base, const RuleItem* item, int amount)
{
	auto cleanUpContainer = [&](ItemContainer* container, const RuleItem* rule, int toRemove) -> int
	{
		int curr = container->getItem(rule);
		if (curr >= toRemove)
		{
			container->removeItem(rule, toRemove);
			return 0;
		}
		else
		{
			container->removeItem(rule, INT_MAX);
			return toRemove - curr;
		}
	};

	auto cleanUpCraft = [&](Craft* craft2, const RuleItem* rule, int toRemove) -> int
	{
		struct S
		{
			int ToRemove, ToSave;
			const RuleItem* rule;
		};

		auto tryRemove = [&toRemove, rule](int curr, const RuleItem* i) -> S
		{
			if (i == rule)
			{
				int r = std::min(toRemove, curr);
				toRemove -= r;
				curr -= r;
				return S{ r, curr, i };
			}
			else
			{
				return S{ 0, curr, i };
			}
		};
		auto tryStore = [&](S s)
		{
			if (s.ToSave > 0)
			{
				base->getStorageItems()->addItem(s.rule, s.ToSave);
			}
		};

		for (auto*& w : *craft2->getWeapons())
		{
			if (w != nullptr)
			{
				auto* wr = w->getRules();

				auto launcher = tryRemove(1, wr->getLauncherItem());
				auto clip = tryRemove(w->getClipsLoaded(), wr->getClipItem());
				if (launcher.ToRemove || clip.ToRemove)
				{
					tryStore(launcher);
					tryStore(clip);

					delete w;
					w = nullptr;
				}
			}
		}

		Collections::deleteIf(
			*craft2->getVehicles(),
			[&](Vehicle* v)
			{
				auto* clipType = v->getRules()->getVehicleClipAmmo();

				auto launcher = tryRemove(1, v->getRules());
				auto clip = tryRemove(v->getRules()->getVehicleClipsLoaded(), clipType);

				if (launcher.ToRemove || clip.ToRemove)
				{
					tryStore(launcher);
					tryStore(clip);

					return true;
				}
				else
				{
					return false;
				}
			}
		);

		return toRemove;
	};

	// remove all of said items from base
	int toRemove = cleanUpContainer(base->getStorageItems(), item, amount);

	// if we still need to remove any, remove them from the crafts first, and keep a running tally
	for (auto* craft : *base->getCrafts())
	{
		if (toRemove <= 0) break; // loop finished
		toRemove = cleanUpContainer(craft->getItems(), item, toRemove);
		if (toRemove > 0)
		{
			toRemove = cleanUpCraft(craft, item, toRemove);
		}
	}

	// if there are STILL any left to remove, take them from the transfers, and if necessary, delete it.
	for (auto transferIt = base->getTransfers()->begin(); transferIt != base->getTransfers()->end() && toRemove;)
	{
		auto* transfer = (*transferIt);
		if (transfer->getItems() == item)
		{
			if (transfer->getQuantity() <= toRemove)
			{
				toRemove -= transfer->getQuantity();
				delete transfer;
				transferIt = base->getTransfers()->erase(transferIt);
			}
			else
			{
				transfer->setItems(transfer->getItems(), transfer->getQuantity() - toRemove);
				toRemove = 0;
			}
		}
		else
		{
			if (transfer->getCraft())
			{
				toRemove = cleanUpContainer(transfer->getCraft()->getItems(), item, toRemove);
				if (toRemove > 0)
				{
					toRemove = cleanUpCraft(transfer->getCraft(), item, toRemove);
				}
			}
			++transferIt;
		}
	}
}

// ---- PRD-J10: apply notification (live screen refresh) -----------------------
// ONE listener, last-registered-wins. `g_listenerOwner` is the identity token that
// makes the "last-registered-wins" rule safe: OXCE defers deleting a popped state
// to the top of the NEXT frame, i.e. AFTER the replacement screen's init() has
// already registered. Without the token the old screen's destructor would clear
// the new screen's listener and refresh would silently die after one rebuild.
const void* g_listenerOwner = nullptr;
ApplyListener g_listener;
std::atomic<int> g_lastApplySeat{-1};

void fireApplyListener(const std::string& cmd, int baseId, int seat)
{
	g_lastApplySeat = seat;
	if (g_listener) g_listener(cmd, baseId);
}

// ---- Shared J05 helpers ------------------------------------------------------

// Serialize a soldier to a YAML string (same wire form giftSoldier uses), so a
// host-generated hire can travel INSIDE shared_apply and be reconstructed on the
// replica without re-rolling RNG (names/stats/nationality would diverge).
std::string serializeSoldier(Game* game, Soldier* soldier)
{
	YAML::YamlRootNodeWriter writer;
	writer.setAsMap();
	soldier->save(writer["soldier"], game->getMod()->getScriptGlobal());
	return writer.emit().yaml;
}

// Reconstruct a soldier from a serialized YAML string. The replica NEVER
// regenerates; it adopts the host's exact soldier (incl. ownerplayerid).
Soldier* deserializeSoldier(Game* game, const std::string& yaml)
{
	YAML::YamlRootNodeReader reader(YAML::YamlString{yaml}, "sharedHire");
	auto soldierReader = reader["soldier"];
	std::string type = soldierReader["type"].readVal(game->getMod()->getSoldiersList().front());
	RuleSoldier* rule = game->getMod()->getSoldier(type, false);
	if (!rule) return nullptr;
	Soldier* soldier = new Soldier(rule, nullptr, 0 /*nationality; overwritten by load*/);
	soldier->load(soldierReader, game->getMod(), game->getSavedGame(), game->getMod()->getScriptGlobal());
	soldier->setCraft(0);
	return soldier;
}

// Shortest base-to-base distance, byte-identical to TransferItemsState::getDistance
// (both bases are real shared bases with identical coords on host and replica).
double baseDistance(Base* from, Base* to)
{
	double x[3], y[3], z[3], r = 51.2;
	Base* b = from;
	for (int i = 0; i < 2; ++i)
	{
		x[i] = r * cos(b->getLatitude()) * cos(b->getLongitude());
		y[i] = r * cos(b->getLatitude()) * sin(b->getLongitude());
		z[i] = r * -sin(b->getLatitude());
		b = to;
	}
	x[2] = x[1] - x[0];
	y[2] = y[1] - y[0];
	z[2] = z[1] - z[0];
	return sqrt(x[2] * x[2] + y[2] * y[2] + z[2] * z[2]);
}

// Find a craft at @a base by its per-type id + rule type (Craft::getId() is only
// unique within a type). Matches TransferItemsState / SellState identity.
Craft* findCraft(Base* base, int id, const std::string& type)
{
	for (auto* c : *base->getCrafts())
		if (c->getId() == id && c->getRules()->getType() == type) return c;
	return nullptr;
}

// A replica takes a craft id the host minted. Keep this machine's per-type
// counter past it, so the replica's counter matches the host's after the apply.
void adoptCraftId(SavedGame* save, const std::string& type, int id)
{
	std::map<std::string, int> ids = save->getAllIds();
	if (ids[type] <= id)
	{
		ids[type] = id + 1;
		save->setAllIds(ids);
	}
}

// True when @a base already holds the craft (type, id), docked or in transit.
bool baseHasCraft(Base* base, int id, const std::string& type)
{
	if (findCraft(base, id, type)) return true;
	for (auto* t : *base->getTransfers())
		if (t && t->getCraft() && t->getCraft()->getId() == id
			&& t->getCraft()->getRules()->getType() == type) return true;
	return false;
}

// Find a soldier at @a base by its vanilla unique id (Soldier::getId(), stable
// across the shared world lineage - the same identity sack/sell match on).
Soldier* findSoldier(Base* base, int id)
{
	if (!base) return nullptr;
	for (auto* s : *base->getSoldiers())
		if (s->getId() == id) return s;
	return nullptr;
}

// PRD-J06: a research project / a production is keyed by its ruleset NAME, which
// is UNIQUE per base: SavedGame::getAvailableResearchProjects /
// getAvailableProductions both exclude a rule already running at the base, and
// the res_start / man_start validators re-run that availability check, so a
// second start of the same rule is rejected. No per-entity sequence id needed
// (verified against vanilla; see session notes).
ResearchProject* findResearchProject(Base* base, const std::string& name)
{
	for (auto* p : base->getResearch())
		if (p->getRules()->getName() == name) return p;
	return nullptr;
}
Production* findProduction(Base* base, const std::string& name)
{
	for (auto* p : base->getProductions())
		if (p->getRules()->getName() == name) return p;
	return nullptr;
}

// ---- Reference command: "buy" ------------------------------------------------
// Payload: { items:[ {type:<TransferType int>, rule:"<typeString>", qty:int}, ...],
//            total:int (client estimate, NOT trusted) }.
//
// J03 supports ITEM / SCIENTIST / ENGINEER / CRAFT deterministically (identical
// transfers on host and replica). SOLDIER hire is deferred to J05: a generated
// soldier carries RNG (nationality/name/stats) that would diverge between host
// and replica unless serialized into shared_apply; the validator rejects soldier
// rows so nothing diverges before J05 wires the serialization.

bool buyValidate(Game* game, const Json::Value& payload, Base* base, int /*seat*/,
                 int64_t& cost, std::string& failReason)
{
	if (!base) { failReason = "base not found"; return false; }
	SavedGame* save = game->getSavedGame();
	Mod* mod = game->getMod();
	if (!save || !mod) { failReason = "no world"; return false; }

	const Json::Value& items = payload["items"];
	if (!items.isArray() || items.empty()) { failReason = "empty purchase"; return false; }

	int64_t total = 0;
	double storeAdd = 0.0;
	int quartersAdd = 0;
	int hangarsAdd = 0;
	std::map<int, int> prisonAdd;

	for (const auto& it : items)
	{
		int type = it.get("type", -1).asInt();
		std::string rule = it.get("rule", "").asString();
		int qty = it.get("qty", 0).asInt();
		if (qty <= 0) continue;
		switch (type)
		{
		case TRANSFER_ITEM:
		{
			RuleItem* r = mod->getItem(rule, false);
			if (!r) { failReason = "unknown item: " + rule; return false; }
			total += (int64_t)qty * r->getBuyCostAdjusted(base, save);
			storeAdd += (double)qty * r->getSize();
			if (r->isAlien()) prisonAdd[r->getPrisonType()] += qty;
			break;
		}
		case TRANSFER_SCIENTIST:
			total += (int64_t)qty * mod->getHireScientistCost();
			quartersAdd += qty;
			break;
		case TRANSFER_ENGINEER:
			total += (int64_t)qty * mod->getHireEngineerCost();
			quartersAdd += qty;
			break;
		case TRANSFER_CRAFT:
		{
			RuleCraft* r = mod->getCraft(rule, false);
			if (!r) { failReason = "unknown craft: " + rule; return false; }
			total += (int64_t)qty * r->getBuyCost();
			hangarsAdd += qty;
			break;
		}
		case TRANSFER_SOLDIER:
		{
			// PRD-J05: hired soldiers spend the command purchaser's funds; the purchaser owns them
			// (setOwnerPlayerId at apply). The host GENERATES them (RNG) at apply
			// time and serializes each into the shared_apply payload so replicas
			// reconstruct rather than re-roll.
			RuleSoldier* r = mod->getSoldier(rule, false);
			if (!r) { failReason = "unknown soldier: " + rule; return false; }
			total += (int64_t)qty * r->getBuyCost();
			quartersAdd += qty; // a hired soldier occupies living quarters
			break;
		}
		default:
			failReason = "unknown transfer type";
			return false;
		}
	}

	// Funds checked first so an insufficient-funds rejection is unambiguous.
	if (save->getFunds() < total) { failReason = "STR_NOT_ENOUGH_MONEY"; return false; }
	// Only gate on store space when the order actually adds store volume. A
	// personnel-only hire (soldier/scientist/engineer) has storeAdd==0 and needs no
	// stores, so it must never be blocked just because existing stores are already
	// full - storesOverfull(0.0) is true whenever the base is at/over capacity.
	if (storeAdd > 0.0 && base->storesOverfull(storeAdd))
		{ failReason = "STR_NOT_ENOUGH_STORE_SPACE"; return false; }
	if (quartersAdd > base->getAvailableQuarters() - base->getUsedQuarters())
		{ failReason = "STR_NOT_ENOUGH_LIVING_SPACE"; return false; }
	if (hangarsAdd > base->getAvailableHangars() - base->getUsedHangars())
		{ failReason = "STR_NO_FREE_HANGARS_FOR_PURCHASE"; return false; }
	for (const auto& kv : prisonAdd)
		if (kv.second > base->getAvailableContainment(kv.first) - base->getUsedContainment(kv.first))
			{ failReason = "STR_NOT_ENOUGH_PRISON_SPACE"; return false; }

	cost = total;
	return true;
}

void buyApply(Game* game, Json::Value& payload, Base* base, int seat)
{
	if (!base) return;
	SavedGame* save = game->getSavedGame();
	Mod* mod = game->getMod();
	if (!save || !mod) return;
	auto& limitLog = save->getMonthlyPurchaseLimitLog();
	const bool host = connectionTCP::getHost();
	const std::string transferOwner = connectionTCP::seatName(seat);

	Json::Value& items = payload["items"];
	if (!items.isArray()) return;

	// Index-based iteration so the host can WRITE resolved soldier YAML back into
	// each soldier row before the payload is broadcast (see buyApply's soldier case).
	for (Json::ArrayIndex i = 0; i < items.size(); ++i)
	{
		Json::Value& it = items[i];
		int type = it.get("type", -1).asInt();
		std::string rule = it.get("rule", "").asString();
		int qty = it.get("qty", 0).asInt();
		if (qty <= 0) continue;
		switch (type)
		{
		case TRANSFER_ITEM:
		{
			RuleItem* r = mod->getItem(rule, false);
			if (!r) break;
			if (r->getMonthlyBuyLimit() > 0) limitLog[r->getType()] += qty;
			Transfer* t = new Transfer(r->getTransferTime());
			t->setOwnerPlayerName(transferOwner);
			t->setItems(r, qty);
			base->getTransfers()->push_back(t);
			// A purchase from the "not enough equipment" screen lowers the missing
			// counts of every such screen on this machine (screen state, not world state; vanilla PurchaseState :940-:944).
			if (payload.get("reequip", false).asBool())
				for (auto* st : game->getStates())
					if (auto* cannot = dynamic_cast<CannotReequipState*>(st)) cannot->decreaseMissingItemCount(r, qty);
			break;
		}
		case TRANSFER_SCIENTIST:
		{
			Transfer* t = new Transfer(mod->getPersonnelTime());
			t->setOwnerPlayerName(transferOwner);
			t->setScientists(qty);
			base->getTransfers()->push_back(t);
			break;
		}
		case TRANSFER_ENGINEER:
		{
			Transfer* t = new Transfer(mod->getPersonnelTime());
			t->setOwnerPlayerName(transferOwner);
			t->setEngineers(qty);
			base->getTransfers()->push_back(t);
			break;
		}
		case TRANSFER_CRAFT:
		{
			RuleCraft* r = mod->getCraft(rule, false);
			if (!r) break;
			if (r->getMonthlyBuyLimit() > 0) limitLog[r->getType()] += qty;
			// The host mints each craft id and writes it into the payload; the
			// replica takes it from there. Counter lock-step alone is not enough:
			// the host also mints craft ids the replica never sees (an hourly
			// production unit, an event's reward craft).
			const bool mint = host && !it.isMember("craftIds");
			Json::Value minted(Json::arrayValue);
			for (int c = 0; c < qty; ++c)
			{
				Transfer* t = new Transfer(r->getTransferTime());
				t->setOwnerPlayerName(transferOwner);
				int craftId = 0;
				if (mint)
				{
					craftId = save->getId(r->getType());
					minted.append(craftId);
				}
				else if (it.isMember("craftIds") && c < (int)it["craftIds"].size())
				{
					craftId = it["craftIds"][c].asInt();
					adoptCraftId(save, r->getType(), craftId);
				}
				else
				{
					craftId = save->getId(r->getType()); // older host: no ids sent
				}
				Craft* craft = new Craft(r, base, craftId);
				craft->initFixedWeapons(mod);
				craft->setStatus("STR_REFUELLING");
				t->setCraft(craft);
				base->getTransfers()->push_back(t);
			}
			if (mint) it["craftIds"] = minted; // travels in shared_apply to the replicas
			break;
		}
		case TRANSFER_SOLDIER:
		{
			RuleSoldier* r = mod->getSoldier(rule, false);
			if (!r) break;
			if (r->getMonthlyBuyLimit() > 0) limitLog[r->getType()] += qty;
			int time = r->getTransferTime();
			if (time == 0) time = mod->getPersonnelTime();

			if (host && !it.isMember("soldiers"))
			{
				// HOST first-apply: generate each soldier (RNG), stamp the
				// purchaser as owner, create the in-transit Transfer, and serialize
				// the finished soldier INTO the payload so the broadcast carries it.
				Json::Value serialized(Json::arrayValue);
				for (int s = 0; s < qty; ++s)
				{
					int nationality = save->selectSoldierNationalityByLocation(mod, r, base);
					Soldier* soldier = mod->genSoldier(save, r, nationality);
					if (!r->getSpawnedSoldierTemplate().yaml.empty())
					{
						YAML::YamlRootNodeReader tReader(r->getSpawnedSoldierTemplate(), "(spawned soldier template)");
						int nationalityOrig = soldier->getNationality();
						soldier->load(tReader.toBase(), mod, save, mod->getScriptGlobal(), true);
						if (soldier->getNationality() != nationalityOrig) soldier->genName();
					}
					soldier->setOwnerPlayerId(it.get("owner", seat).asInt()); // purchaser owns the hire; a shared list's Soldier-row editor
					Transfer* t = new Transfer(time);
					t->setOwnerPlayerName(transferOwner);
					t->setSoldier(soldier);
					base->getTransfers()->push_back(t);
					serialized.append(serializeSoldier(game, soldier));
				}
				it["soldiers"] = serialized; // travels in shared_apply to the replicas
			}
			else
			{
				// REPLICA (or a re-apply carrying resolved soldiers): reconstruct the
				// host's exact soldiers from the serialized YAML - never re-roll.
				const Json::Value& serialized = it["soldiers"];
				for (Json::ArrayIndex s = 0; s < serialized.size(); ++s)
				{
					Soldier* soldier = deserializeSoldier(game, serialized[s].asString());
					if (!soldier) continue;
					soldier->setOwnerPlayerId(it.get("owner", seat).asInt()); // belt-and-braces (also in YAML)
					Transfer* t = new Transfer(time);
					t->setOwnerPlayerName(transferOwner);
					t->setSoldier(soldier);
					base->getTransfers()->push_back(t);
				}
			}
			break;
		}
		default:
			break;
		}
	}
	if (payload.isMember("selKey")) selConsume(payload); // the shared list is consumed
}

// ---- PRD-J05: "sell" ---------------------------------------------------------
// Payload: { items:[{rule, qty}], soldiers:[id...], crafts:[{id,type}...],
//            scientists:int, engineers:int }. baseId = the base being sold from.
// Vanilla sell is atomic (one OK button, immediate removal + credit). The host
// re-prices against the live world (another player may have sold first); any
// missing quantity rejects the WHOLE command. cost is NEGATIVE (a credit).

bool sellValidate(Game* game, const Json::Value& payload, Base* base, int /*seat*/,
                  int64_t& cost, std::string& failReason)
{
	if (!base) { failReason = "base not found"; return false; }
	// A forced storage confirm that arrives after
	// the base is back under its limit is dropped silently (checked FIRST); otherwise it may sell what the forced
	// screen lists - the crafts' and in-transit items too, as vanilla.
	const bool forced = payload.get("origin", "").asString() == "forced";
	if (forced && storageSolved(base)) { failReason = "coop_forced_resolved"; return false; }
	const bool critical = forced && base->storesOverfullCritical();
	SavedGame* save = game->getSavedGame();
	Mod* mod = game->getMod();
	if (!save || !mod) { failReason = "no world"; return false; }

	int64_t credit = 0;

	const Json::Value& items = payload["items"];
	if (items.isArray())
		for (const auto& it : items)
		{
			std::string rule = it.get("rule", "").asString();
			int qty = it.get("qty", 0).asInt();
			if (qty <= 0) continue;
			RuleItem* r = mod->getItem(rule, false);
			if (!r) { failReason = "unknown item: " + rule; return false; }
			if (payload.get("capToStores", false).asBool()) qty = std::min(qty, base->getStorageItems()->getItem(r)); // sell what is left
			if ((forced ? forcedSellAvailable(base, r, critical) : base->getStorageItems()->getItem(r)) < qty)
				{ failReason = "STR_NOT_ENOUGH_ITEMS_TO_SELL"; return false; }
			credit += (int64_t)qty * r->getSellCostAdjusted(base, save);
		}

	const Json::Value& soldiers = payload["soldiers"];
	if (soldiers.isArray())
		for (const auto& sid : soldiers)
		{
			int id = sid.asInt();
			bool found = false;
			for (auto* s : *base->getSoldiers())
				if (s->getId() == id && s->getCraft() == 0) { found = true; break; }
			if (!found) { failReason = "soldier not sellable"; return false; }
		}

	const Json::Value& crafts = payload["crafts"];
	if (crafts.isArray())
		for (const auto& jc : crafts)
		{
			Craft* c = findCraft(base, jc.get("id", -1).asInt(), jc.get("type", "").asString());
			if (!c || c->getStatus() == "STR_OUT") { failReason = "craft not sellable"; return false; }
			credit += c->getRules()->getSellCost();
		}

	int sci = payload.get("scientists", 0).asInt();
	int eng = payload.get("engineers", 0).asInt();
	if (sci > base->getAvailableScientists()) { failReason = "not enough scientists"; return false; }
	if (eng > base->getAvailableEngineers()) { failReason = "not enough engineers"; return false; }

	cost = -credit; // credit the seller
	return true;
}

void sellApply(Game* game, Json::Value& payload, Base* base, int /*seat*/)
{
	if (!base) return;
	Mod* mod = game->getMod();
	if (!mod) return;

	// A capped sale (the random-production window) sells what the host's stores still hold; the host
	// writes the count it sold into the broadcast payload, so every replica removes the same.
	if (connectionTCP::getHost() && payload.get("capToStores", false).asBool())
		for (Json::ArrayIndex i = 0; i < payload["items"].size(); ++i)
			if (RuleItem* r = mod->getItem(payload["items"][i].get("rule", "").asString(), false))
				payload["items"][i]["qty"] = std::min(payload["items"][i].get("qty", 0).asInt(), base->getStorageItems()->getItem(r));
	// ORDER (items -> soldiers -> crafts -> scientists -> engineers) is fixed and
	// identical on host and replica, so both worlds mutate the same way.
	// a forced storage sale removes in vanilla's order (stock, crafts, transfers).
	const bool forced = payload.get("origin", "").asString() == "forced";
	const Json::Value& items = payload["items"];
	if (items.isArray())
		for (const auto& it : items)
		{
			int qty = it.get("qty", 0).asInt();
			RuleItem* r = mod->getItem(it.get("rule", "").asString(), false);
			if (r && qty > 0 && forced) forcedSellRemove(base, r, qty);
			else if (r && qty > 0) base->getStorageItems()->removeItem(r, qty);
		}

	const Json::Value& soldiers = payload["soldiers"];
	if (soldiers.isArray())
		for (const auto& sid : soldiers)
		{
			int id = sid.asInt();
			for (auto it = base->getSoldiers()->begin(); it != base->getSoldiers()->end(); ++it)
			{
				Soldier* s = *it;
				if (s->getId() == id && s->getCraft() == 0)
				{
					if (s->getArmor()->getStoreItem())
						base->getStorageItems()->addItem(s->getArmor()->getStoreItem());
					base->getSoldiers()->erase(it);
					delete s;
					break;
				}
			}
		}

	const Json::Value& crafts = payload["crafts"];
	if (crafts.isArray())
		for (const auto& jc : crafts)
		{
			Craft* c = findCraft(base, jc.get("id", -1).asInt(), jc.get("type", "").asString());
			if (c) { base->removeCraft(c, true); delete c; }
		}

	int sci = payload.get("scientists", 0).asInt();
	int eng = payload.get("engineers", 0).asInt();
	if (sci > 0) base->setScientists(base->getScientists() - sci);
	if (eng > 0) base->setEngineers(base->getEngineers() - eng);
	// a page-3 sale's bookkeeping (autosell marks, open debriefing counts).
	if (payload.get("debrief", false).asBool()) connectionTCP::coopDebriefRecoveredSold(game, payload, true);
	if (payload.isMember("selKey")) selConsume(payload); // the shared list is consumed
}

// ---- PRD-J05: "containment" --------------------------------------------------
// Payload: { prisoners:[{rule, qty}], sell:bool }. Mirrors
// ManageAlienContainmentState::dealWithSelectedAliens: remove live aliens from
// storage; if sell -> credit funds (host-authoritative), else (execute) -> add
// the geoscape corpse. Atomic re-price on the host.

bool containmentValidate(Game* game, const Json::Value& payload, Base* base, int /*seat*/,
                         int64_t& cost, std::string& failReason)
{
	if (!base) { failReason = "base not found"; return false; }
	// a forced containment confirm that arrives after the prison is
	// back under its limit is dropped silently (checked FIRST).
	if (payload.get("origin", "").asString() == "forced" && containmentSolved(base, payload.get("prisonType", 0).asInt()))
		{ failReason = "coop_forced_resolved"; return false; }
	SavedGame* save = game->getSavedGame();
	Mod* mod = game->getMod();
	if (!save || !mod) { failReason = "no world"; return false; }
	bool sell = payload.get("sell", false).asBool();

	int64_t credit = 0;
	const Json::Value& prisoners = payload["prisoners"];
	if (!prisoners.isArray() || prisoners.empty()) { failReason = "no prisoners"; return false; }
	for (const auto& p : prisoners)
	{
		std::string rule = p.get("rule", "").asString();
		int qty = p.get("qty", 0).asInt();
		if (qty <= 0) continue;
		RuleItem* r = mod->getItem(rule, false);
		if (!r) { failReason = "unknown alien: " + rule; return false; }
		if (base->getStorageItems()->getItem(r) < qty)
			{ failReason = "STR_NOT_ENOUGH_PRISONERS"; return false; }
		if (sell) credit += (int64_t)qty * r->getSellCostAdjusted(base, save);
	}
	cost = sell ? -credit : 0;
	return true;
}

void containmentApply(Game* game, Json::Value& payload, Base* base, int /*seat*/)
{
	if (!base) return;
	Mod* mod = game->getMod();
	if (!mod) return;
	bool sell = payload.get("sell", false).asBool();

	const Json::Value& prisoners = payload["prisoners"];
	if (!prisoners.isArray()) return;
	for (const auto& p : prisoners)
	{
		std::string rule = p.get("rule", "").asString();
		int qty = p.get("qty", 0).asInt();
		if (qty <= 0) continue;
		RuleItem* r = mod->getItem(rule, false);
		if (!r) continue;
		base->getStorageItems()->removeItem(r, qty);
		if (!sell)
		{
			// Execute: leave the geoscape corpse behind (funds untouched).
			Unit* ruleUnit = mod->getUnit(rule, false);
			if (ruleUnit)
			{
				auto* ruleCorpse = ruleUnit->getArmor()->getCorpseGeoscape();
				if (ruleCorpse && ruleCorpse->isRecoverable() && ruleCorpse->isCorpseRecoverable())
					base->getStorageItems()->addItem(ruleCorpse, qty);
			}
		}
	}
	if (payload.isMember("selKey")) selConsume(payload); // the shared list is consumed
}

// ---- PRD-J05: "transfer" (intra-world base -> base) --------------------------
// Payload: { toBaseId:int, items:[{rule, qty}], soldiers:[id...],
//            crafts:[{id,type}...], scientists:int, engineers:int }.
// baseId = SOURCE base. SHARED transfers are vanilla intra-world moves (cost +
// travel time), NOT the SEPARATE cross-player syncTrade flow. The created
// Transfer objects arrive later via the J04 transfer_arrived broadcast, so host
// and replica must build them in identical order (they run the same applier).

bool transferValidate(Game* game, const Json::Value& payload, Base* fromBase, int /*seat*/,
                      int64_t& cost, std::string& failReason)
{
	if (!fromBase) { failReason = "source base not found"; return false; }
	SavedGame* save = game->getSavedGame();
	Mod* mod = game->getMod();
	if (!save || !mod) { failReason = "no world"; return false; }

	Base* toBase = resolveBase(game, payload.get("toBaseId", -1).asInt());
	if (!toBase || toBase == fromBase) { failReason = "bad destination base"; return false; }

	double distance = baseDistance(fromBase, toBase);
	int itemCost = (int)(1 * distance);
	int soldierCost = (int)(5 * distance);
	int craftCost = (int)(25 * distance);
	int sciCost = (int)(5 * distance);
	int engCost = (int)(5 * distance);

	int64_t total = 0;
	double storeAddTo = 0.0;
	// Live aliens per prison type: the destination must hold them, exactly as
	// the vanilla TransferItemsState gate does (any containment of that type
	// without storage limits; free containment space with them).
	std::map<int, int> incomingPrisoners;

	const Json::Value& items = payload["items"];
	if (items.isArray())
		for (const auto& it : items)
		{
			std::string rule = it.get("rule", "").asString();
			int qty = it.get("qty", 0).asInt();
			if (qty <= 0) continue;
			RuleItem* r = mod->getItem(rule, false);
			if (!r) { failReason = "unknown item: " + rule; return false; }
			if (fromBase->getStorageItems()->getItem(r) < qty)
				{ failReason = "STR_NOT_ENOUGH_ITEMS_TO_TRANSFER"; return false; }
			total += (int64_t)qty * itemCost;
			storeAddTo += (double)qty * r->getSize();
			if (r->isAlien())
				incomingPrisoners[r->getPrisonType()] += qty;
		}
	for (const auto& prisoners : incomingPrisoners)
	{
		const int available = toBase->getAvailableContainment(prisoners.first);
		const int room = Options::storageLimitsEnforced
			? available - toBase->getUsedContainment(prisoners.first)
			: (available > 0 ? prisoners.second : 0);
		if (prisoners.second > room)
			{ failReason = "STR_NO_ALIEN_CONTAINMENT_FOR_TRANSFER"; return false; }
	}

	// Living quarters: the base that HOUSES a soldier pays for it, and the
	// destination reserves the space the moment the transfer is sent
	// (Base::getTotalSoldiers already counts personnel en route). Refuse a move
	// the destination cannot house, the same way the store limit is enforced.
	int incomingPersonnel = 0;

	const Json::Value& soldiers = payload["soldiers"];
	if (soldiers.isArray())
		for (const auto& sid : soldiers)
		{
			int id = sid.asInt();
			bool found = false;
			for (auto* s : *fromBase->getSoldiers())
				if (s->getId() == id && s->getCraft() == 0) { found = true; break; }
			if (!found) { failReason = "soldier not transferable"; return false; }
			total += soldierCost;
			incomingPersonnel++;
		}

	int incomingCrafts = 0;
	const Json::Value& crafts = payload["crafts"];
	if (crafts.isArray())
		for (const auto& jc : crafts)
		{
			Craft* c = findCraft(fromBase, jc.get("id", -1).asInt(), jc.get("type", "").asString());
			if (!c) { failReason = "craft not transferable"; return false; }
			total += craftCost;
			incomingCrafts++;
			// the crew rides along (see transferApply) and must be housed too
			for (auto* s : *fromBase->getSoldiers())
				if (s->getCraft() == c) incomingPersonnel++;
		}

	int sci = payload.get("scientists", 0).asInt();
	int eng = payload.get("engineers", 0).asInt();
	if (sci > fromBase->getAvailableScientists()) { failReason = "not enough scientists"; return false; }
	if (eng > fromBase->getAvailableEngineers()) { failReason = "not enough engineers"; return false; }
	total += (int64_t)sci * sciCost;
	total += (int64_t)eng * engCost;

	incomingPersonnel += sci + eng;

	if (save->getFunds() < total) { failReason = "STR_NOT_ENOUGH_MONEY"; return false; }
	if (Options::storageLimitsEnforced && toBase->storesOverfull(storeAddTo))
		{ failReason = "STR_NOT_ENOUGH_STORE_SPACE"; return false; }
	if (incomingCrafts > 0
		&& toBase->getAvailableHangars() - toBase->getUsedHangars() < incomingCrafts)
		{ failReason = "STR_NO_FREE_HANGARS_FOR_TRANSFER"; return false; }
	if (incomingPersonnel > 0
		&& toBase->getAvailableQuarters() - toBase->getUsedQuarters() < incomingPersonnel)
		{ failReason = "STR_NO_FREE_ACCOMODATION"; return false; }

	cost = total; // positive debit
	return true;
}

void transferApply(Game* game, Json::Value& payload, Base* fromBase, int seat)
{
	if (!fromBase) return;
	Mod* mod = game->getMod();
	if (!mod) return;
	Base* toBase = resolveBase(game, payload.get("toBaseId", -1).asInt());
	if (!toBase) return;
	const std::string transferOwner = connectionTCP::seatName(seat);

	double distance = baseDistance(fromBase, toBase);
	int time = (int)floor(6 + distance / 10.0);

	const Json::Value& items = payload["items"];
	if (items.isArray())
		for (const auto& it : items)
		{
			int qty = it.get("qty", 0).asInt();
			RuleItem* r = mod->getItem(it.get("rule", "").asString(), false);
			if (!r || qty <= 0) continue;
			fromBase->getStorageItems()->removeItem(r, qty);
			Transfer* t = new Transfer(time);
			t->setOwnerPlayerName(transferOwner);
			t->setItems(r, qty);
			toBase->getTransfers()->push_back(t);
		}

	const Json::Value& soldiers = payload["soldiers"];
	// Separate only (TransferItemsState::submitSharedTransfer): the sender's
	// option was OFF and the soldier goes to another player's base.
	const bool stripLayout = payload.get("stripLayout", false).asBool();
	if (soldiers.isArray())
		for (const auto& sid : soldiers)
		{
			int id = sid.asInt();
			for (auto it = fromBase->getSoldiers()->begin(); it != fromBase->getSoldiers()->end(); ++it)
			{
				Soldier* s = *it;
				if (s->getId() == id && s->getCraft() == 0)
				{
					s->setPsiTraining(false);
					if (s->isInTraining()) s->setReturnToTrainingWhenHealed(true);
					s->setTraining(false);
					if (stripLayout) s->clearEquipmentLayout();
					// Ownership unchanged by a transfer (PRD-J05).
					Transfer* t = new Transfer(time);
					t->setOwnerPlayerName(connectionTCP::seatName(s->getOwnerPlayerId()));
					t->setSoldier(s);
					toBase->getTransfers()->push_back(t);
					fromBase->getSoldiers()->erase(it);
					break;
				}
			}
		}

	const Json::Value& crafts = payload["crafts"];
	if (crafts.isArray())
		for (const auto& jc : crafts)
		{
			Craft* craft = findCraft(fromBase, jc.get("id", -1).asInt(), jc.get("type", "").asString());
			if (!craft) continue;
			// Move the craft's assigned soldiers with it (non-airborne path).
			for (auto it = fromBase->getSoldiers()->begin(); it != fromBase->getSoldiers()->end();)
			{
				Soldier* s = *it;
				if (s->getCraft() == craft)
				{
					s->setPsiTraining(false);
					if (s->isInTraining()) s->setReturnToTrainingWhenHealed(true);
					s->setTraining(false);
					Transfer* t = new Transfer(time);
					t->setOwnerPlayerName(connectionTCP::seatName(s->getOwnerPlayerId()));
					t->setSoldier(s);
					toBase->getTransfers()->push_back(t);
					it = fromBase->getSoldiers()->erase(it);
				}
				else ++it;
			}
			fromBase->removeCraft(craft, false);
			Transfer* t = new Transfer(time);
			t->setOwnerPlayerName(transferOwner);
			t->setCraft(craft);
			toBase->getTransfers()->push_back(t);
		}

	int sci = payload.get("scientists", 0).asInt();
	int eng = payload.get("engineers", 0).asInt();
	if (sci > 0)
	{
		fromBase->setScientists(fromBase->getScientists() - sci);
		Transfer* t = new Transfer(time);
		t->setOwnerPlayerName(transferOwner);
		t->setScientists(sci);
		toBase->getTransfers()->push_back(t);
	}
	if (eng > 0)
	{
		fromBase->setEngineers(fromBase->getEngineers() - eng);
		Transfer* t = new Transfer(time);
		t->setOwnerPlayerName(transferOwner);
		t->setEngineers(eng);
		toBase->getTransfers()->push_back(t);
	}
	// a page-3 transfer's bookkeeping (the open debriefing's counts).
	if (payload.get("debrief", false).asBool()) connectionTCP::coopDebriefRecoveredSold(game, payload, false);
	if (payload.isMember("selKey")) selConsume(payload); // the shared list is consumed
}

// ---- PRD-J06: research start / allocate / cancel -----------------------------
// A SHARED research screen mutates NOTHING locally; the OK/Start/Cancel buttons
// emit one of these commands and the host-authoritative world settles via
// shared_apply. Completion stays host-driven (J04 research_done). Research has no
// funds cost, so every validator here sets cost 0 (the apply still carries the
// authoritative funds per the protocol invariant).

// res_start payload: { project:<ruleName> } (+ host-resolved "cost").
bool resStartValidate(Game* game, const Json::Value& payload, Base* base, int /*seat*/,
                      int64_t& cost, std::string& failReason)
{
	if (!base) { failReason = "base not found"; return false; }
	SavedGame* save = game->getSavedGame();
	Mod* mod = game->getMod();
	if (!save || !mod) { failReason = "no world"; return false; }
	std::string pname = payload.get("project", "").asString();
	RuleResearch* rule = mod->getResearch(pname, false);
	if (!rule) { failReason = "unknown research: " + pname; return false; }
	// Availability = rules + not-already-running-here + needed item + base funcs.
	std::vector<RuleResearch*> avail;
	save->getAvailableResearchProjects(avail, mod, base, false);
	bool ok = false;
	for (auto* r : avail) if (r == rule) { ok = true; break; }
	if (!ok) { failReason = "STR_RESEARCH_NOT_AVAILABLE"; return false; }
	cost = 0;
	return true;
}

void resStartApply(Game* game, Json::Value& payload, Base* base, int /*seat*/)
{
	if (!base) return;
	SavedGame* save = game->getSavedGame();
	Mod* mod = game->getMod();
	if (!save || !mod) return;
	std::string pname = payload.get("project", "").asString();
	RuleResearch* rule = mod->getResearch(pname, false);
	if (!rule) return;
	if (findResearchProject(base, pname)) return; // idempotent guard

	// Randomised cost is HOST-only RNG (vanilla ResearchInfoState ctor). Resolve it
	// once on the host, write it into the payload, and let replicas adopt it - the
	// buy-soldier pattern - so host and replica hold the same _cost.
	int projCost;
	if (connectionTCP::getHost() && !payload.isMember("cost"))
	{
		int rng = RNG::generate(50, 150);
		projCost = rule->getCost() * rng / 100;
		if (rule->getCost() > 0) projCost = std::max(1, projCost);
		payload["cost"] = projCost;
	}
	else
	{
		projCost = payload.get("cost", rule->getCost()).asInt();
	}
	ResearchProject* proj = new ResearchProject(rule, projCost);
	base->addResearch(proj); // 0 scientists (allocation is a separate res_alloc)
	// Consume the needed item exactly as the vanilla start does (deterministic).
	if (rule->needItem() && rule->destroyItem())
	{
		if (!SeparateEcon::consumeSharedResearchItem(game, base, rule))
			base->getStorageItems()->removeItem(rule->getNeededItem(), 1);
	}
}

// res_alloc payload: { project:<ruleName>, assigned:<absolute int> }. ABSOLUTE
// target (last-write-wins) so two players adjusting the same project converge
// instead of compounding deltas.
bool resAllocValidate(Game* game, const Json::Value& payload, Base* base, int /*seat*/,
                      int64_t& cost, std::string& failReason)
{
	if (!base) { failReason = "base not found"; return false; }
	std::string pname = payload.get("project", "").asString();
	ResearchProject* proj = findResearchProject(base, pname);
	if (!proj) { failReason = "research not running: " + pname; return false; }
	int target = payload.get("assigned", -1).asInt();
	if (target < 0) { failReason = "bad allocation"; return false; }
	int delta = target - proj->getAssigned();
	if (delta > base->getAvailableScientists()) { failReason = "STR_NOT_ENOUGH_SCIENTISTS"; return false; }
	if (delta > base->getFreeLaboratories()) { failReason = "STR_NOT_ENOUGH_LABORATORY_SPACE"; return false; }
	cost = 0;
	return true;
}

void resAllocApply(Game* game, Json::Value& payload, Base* base, int /*seat*/)
{
	if (!base) return;
	std::string pname = payload.get("project", "").asString();
	ResearchProject* proj = findResearchProject(base, pname);
	if (!proj) return;
	int target = payload.get("assigned", proj->getAssigned()).asInt();
	int delta = target - proj->getAssigned(); // replica's current matches host (FIFO)
	proj->setAssigned(target);
	base->setScientists(base->getScientists() - delta);
}

// res_cancel payload: { project:<ruleName> }.
bool resCancelValidate(Game* game, const Json::Value& payload, Base* base, int /*seat*/,
                       int64_t& cost, std::string& failReason)
{
	if (!base) { failReason = "base not found"; return false; }
	std::string pname = payload.get("project", "").asString();
	if (!findResearchProject(base, pname)) { failReason = "research not running: " + pname; return false; }
	cost = 0;
	return true;
}

void resCancelApply(Game* game, Json::Value& payload, Base* base, int /*seat*/)
{
	if (!base) return;
	std::string pname = payload.get("project", "").asString();
	ResearchProject* proj = findResearchProject(base, pname);
	if (!proj) return;
	// removeResearch frees the assigned scientists AND (if unfinished + needItem +
	// destroyItem) refunds the needed item - identical on host and replica because
	// the project's assigned is kept in lock-step and a running project is
	// not-finished on both sides.
	base->removeResearch(proj);
}

// ---- PRD-J06: manufacture start / allocate / cancel --------------------------
// man_start/man_cancel change funds (first-unit debit / refund); man_alloc does
// not but carries funds anyway (protocol invariant). The host re-validates funds,
// materials, engineer pool + workshop space against the live world.

// man_start payload: { item:<ruleName>, engineers, qty, infinite, sell, fallback }.
bool manStartValidate(Game* game, const Json::Value& payload, Base* base, int /*seat*/,
                      int64_t& cost, std::string& failReason)
{
	if (!base) { failReason = "base not found"; return false; }
	SavedGame* save = game->getSavedGame();
	Mod* mod = game->getMod();
	if (!save || !mod) { failReason = "no world"; return false; }
	std::string item = payload.get("item", "").asString();
	RuleManufacture* rule = mod->getManufacture(item, false);
	if (!rule) { failReason = "unknown manufacture: " + item; return false; }
	// Availability = requirements researched + not-already-producing-here.
	std::vector<RuleManufacture*> avail;
	save->getAvailableProductions(avail, mod, base, MANU_FILTER_DEFAULT);
	bool ok = false;
	for (auto* m : avail) if (m == rule) { ok = true; break; }
	if (!ok) { failReason = "STR_PRODUCTION_NOT_AVAILABLE"; return false; }

	int engineers = payload.get("engineers", 0).asInt();
	if (engineers < 0) { failReason = "bad allocation"; return false; }
	// First-unit gate (vanilla startItem): funds + materials + crafts.
	if (save->getFunds() < rule->getManufactureCost()) { failReason = "STR_NOT_ENOUGH_MONEY"; return false; }
	for (const auto& i : rule->getRequiredItems())
		if (base->getStorageItems()->getItem(i.first) < i.second)
			{ failReason = "STR_NOT_ENOUGH_SPECIAL_MATERIALS"; return false; }
	for (const auto& i : rule->getRequiredCrafts())
		if (base->getCraftCountForProduction(i.first) < i.second)
			{ failReason = "STR_NOT_ENOUGH_SPECIAL_MATERIALS"; return false; }
	// Engineer pool + workshop (flat requiredSpace on activation + one slot each).
	if (engineers > base->getAvailableEngineers()) { failReason = "STR_NOT_ENOUGH_ENGINEERS"; return false; }
	int wsNeed = engineers + (engineers > 0 ? rule->getRequiredSpace() : 0);
	if (wsNeed > base->getFreeWorkshops()) { failReason = "STR_NOT_ENOUGH_WORK_SPACE"; return false; }
	if (rule->getProducedCraft() && base->getAvailableHangars() - base->getUsedHangars() <= 0)
		{ failReason = "STR_NO_FREE_HANGARS_FOR_CRAFT_PRODUCTION"; return false; }
	if (!rule->getSpawnedPersonType().empty() && base->getAvailableQuarters() <= base->getUsedQuarters())
		{ failReason = "STR_NOT_ENOUGH_LIVING_SPACE"; return false; }

	cost = rule->getManufactureCost(); // debit the first unit; protocol adjusts funds
	return true;
}

void manStartApply(Game* game, Json::Value& payload, Base* base, int seat)
{
	if (!base) return;
	Mod* mod = game->getMod();
	if (!mod) return;
	std::string item = payload.get("item", "").asString();
	RuleManufacture* rule = mod->getManufacture(item, false);
	if (!rule) return;
	if (findProduction(base, item)) return; // idempotent guard

	int engineers = payload.get("engineers", 0).asInt();
	int qty = payload.get("qty", 1).asInt();
	if (qty < 1) qty = 1;
	Production* p = new Production(rule, qty);
	p->setInfiniteAmount(payload.get("infinite", false).asBool());
	p->setAssignedEngineers(engineers);
	p->setSellItems(payload.get("sell", false).asBool());
	base->addProduction(p);
	p->setCoopStarterSeat(seat); // the starter owns what it spawns
	base->setEngineers(base->getEngineers() - engineers);
	if (payload.get("fallback", false).asBool())
	{
		for (auto* pp : base->getProductions()) pp->setFallback(false);
		p->setFallback(true);
	}
	// Vanilla startItem's non-funds effects (funds are the protocol's job): remove
	// the first unit's required items + consume one matching required craft each.
	for (const auto& i : rule->getRequiredItems())
		base->getStorageItems()->removeItem(i.first, i.second);
	for (const auto& i : rule->getRequiredCrafts())
	{
		for (auto* c : *base->getCrafts())
		{
			if (c->getRules() == i.first) { base->removeCraft(c, true); delete c; break; }
		}
	}
}

// man_alloc payload: { item, engineers, qty, infinite, sell, fallback } (absolute).
bool manAllocValidate(Game* game, const Json::Value& payload, Base* base, int /*seat*/,
                      int64_t& cost, std::string& failReason)
{
	if (!base) { failReason = "base not found"; return false; }
	std::string item = payload.get("item", "").asString();
	Production* p = findProduction(base, item);
	if (!p) { failReason = "production not running: " + item; return false; }
	int engineers = payload.get("engineers", -1).asInt();
	if (engineers < 0) { failReason = "bad allocation"; return false; }
	int delta = engineers - p->getAssignedEngineers();
	if (delta > base->getAvailableEngineers()) { failReason = "STR_NOT_ENOUGH_ENGINEERS"; return false; }
	int wsNeed = delta;
	if (p->isQueuedOnly() && engineers > 0) wsNeed += p->getRules()->getRequiredSpace();
	if (wsNeed > base->getFreeWorkshops()) { failReason = "STR_NOT_ENOUGH_WORK_SPACE"; return false; }
	cost = 0;
	return true;
}

void manAllocApply(Game* game, Json::Value& payload, Base* base, int /*seat*/)
{
	if (!base) return;
	std::string item = payload.get("item", "").asString();
	Production* p = findProduction(base, item);
	if (!p) return;
	int engineers = payload.get("engineers", p->getAssignedEngineers()).asInt();
	int delta = engineers - p->getAssignedEngineers();
	p->setAssignedEngineers(engineers);
	base->setEngineers(base->getEngineers() - delta);
	p->setInfiniteAmount(payload.get("infinite", p->getInfiniteAmount()).asBool());
	int qty = payload.get("qty", p->getAmountTotal()).asInt();
	if (qty >= 1) p->setAmountTotal(qty);
	p->setSellItems(payload.get("sell", p->getSellItems()).asBool());
	if (payload.get("fallback", false).asBool())
	{
		for (auto* pp : base->getProductions()) pp->setFallback(false);
		p->setFallback(true);
	}
	else p->setFallback(false);
}

// man_cancel payload: { item, refund } (refund re-derived host-side from the rule).
bool manCancelValidate(Game* game, const Json::Value& payload, Base* base, int /*seat*/,
                       int64_t& cost, std::string& failReason)
{
	if (!base) { failReason = "base not found"; return false; }
	std::string item = payload.get("item", "").asString();
	Production* p = findProduction(base, item);
	if (!p) { failReason = "production not running: " + item; return false; }
	// Refund is a property of the rule, not a client choice - re-derive it.
	cost = p->getRules()->getRefund() ? -(int64_t)p->getRules()->getManufactureCost() : 0;
	return true;
}

void manCancelApply(Game* game, Json::Value& payload, Base* base, int /*seat*/)
{
	if (!base) return;
	std::string item = payload.get("item", "").asString();
	Production* p = findProduction(base, item);
	if (!p) return;
	const RuleManufacture* rule = p->getRules();
	if (rule->getRefund())
	{
		// refundItem's non-funds effects (funds via the protocol credit above).
		for (const auto& i : rule->getRequiredItems())
			base->getStorageItems()->addItem(i.first, i.second);
	}
	base->removeProduction(p); // frees engineers, deletes the Production
}

// ---- PRD-J07: facilities, rename, sack, new base, base destroyed -------------
// Shared-base construction/management via shared_cmd. baseId = index into
// getBases() (load-bearing: every command routes by it and base add/remove rides
// shared_apply so host and replicas keep the index in lock-step).

// A transient, headless BaseView so the host validates/applies facility placement
// EXACTLY as the interactive PlaceFacilityState does (connectivity/overlap rules,
// build queue), without a mouse. Caller deletes it.
BaseView* makeGridView(Base* base, int x, int y)
{
	BaseView* v = new BaseView(192, 192, 0, 8);
	v->setBase(base);
	v->setGridPosition(x, y);
	return v;
}

// Accumulate the funds refund + item refunds that placing @a rule at (x,y) would
// yield by building over the facilities it intersects - byte-identical to
// PlaceFacilityState::viewClick's removal loop, but WITHOUT mutating (validator
// side). Funds ride the protocol cost; items are re-derived by the applier.
void accumulateBuildOverRefunds(Game* game, Base* base, const RuleBaseFacility* rule,
                                int gridX, int gridY, int64_t& refundValue,
                                std::map<std::string, int>& refundItems)
{
	refundValue = 0;
	const BaseAreaSubset area = BaseAreaSubset(rule->getSizeX(), rule->getSizeY()).offset(gridX, gridY);
	for (int i = (int)base->getFacilities()->size() - 1; i >= 0; --i)
	{
		BaseFacility* over = base->getFacilities()->at(i);
		if (!BaseAreaSubset::intersection(area, over->getPlacement())) continue;
		const auto& itemCost = over->getRules()->getBuildCostItems();
		if (over->getBuildTime() > over->getRules()->getBuildTime())
		{
			refundValue += over->getRules()->getBuildCost();
			for (auto& it : itemCost) refundItems[it.first] += it.second.first;
		}
		else
		{
			refundValue += over->getRules()->getRefundValue();
			for (auto& it : itemCost) refundItems[it.first] += it.second.second;
		}
		if (over->getAmmo() > 0)
			refundItems[over->getRules()->getAmmoItem()->getType()] += over->getAmmo();
	}
	(void)game;
}

// fac_build payload: { facilityType:<ruleName>, x, y }. Client-originated START of
// a facility build (analogous to man_start). Host re-validates placement + funds +
// items against the live world; the vanilla validity re-check IS the tile-conflict
// guard (two players targeting the same tiles -> loser gets shared_fail).
bool facBuildValidate(Game* game, const Json::Value& payload, Base* base, int /*seat*/,
                      int64_t& cost, std::string& failReason)
{
	if (!base) { failReason = "base not found"; return false; }
	SavedGame* save = game->getSavedGame();
	Mod* mod = game->getMod();
	if (!save || !mod) { failReason = "no world"; return false; }
	RuleBaseFacility* rule = mod->getBaseFacility(payload.get("facilityType", "").asString(), false);
	if (!rule) { failReason = "unknown facility"; return false; }
	// Buildability gates (BuildFacilitiesState/PlaceLiftState list filters).
	if (!save->isResearched(rule->getRequirements()))
		{ failReason = "facility not researched"; return false; }
	if (!rule->isAllowedForBaseType(base->isFakeUnderwater()))
		{ failReason = "facility not allowed for base type"; return false; }
	int x = payload.get("x", -1).asInt();
	int y = payload.get("y", -1).asInt();

	BaseView* v = makeGridView(base, x, y);
	BasePlacementErrors err = v->getPlacementError(rule);
	delete v;
	if (err != BPE_None) { failReason = "STR_CANNOT_BUILD_HERE"; return false; }

	int64_t refundValue = 0;
	std::map<std::string, int> refundItems;
	accumulateBuildOverRefunds(game, base, rule, x, y, refundValue, refundItems);

	int64_t net = (int64_t)rule->getBuildCost() - refundValue;
	if (save->getFunds() < net) { failReason = "STR_NOT_ENOUGH_MONEY"; return false; }
	for (const auto& item : rule->getBuildCostItems())
	{
		int needed = (item.second.first - refundItems[item.first]) - base->getStorageItems()->getItem(item.first);
		if (needed > 0) { failReason = "STR_NOT_ENOUGH_ITEMS"; return false; }
	}
	cost = net; // net debit (build cost minus build-over refunds); funds via protocol
	return true;
}

void facBuildApply(Game* game, Json::Value& payload, Base* base, int /*seat*/)
{
	if (!base) return;
	Mod* mod = game->getMod();
	if (!mod) return;
	RuleBaseFacility* rule = mod->getBaseFacility(payload.get("facilityType", "").asString(), false);
	if (!rule) return;
	int gridX = payload.get("x", -1).asInt();
	int gridY = payload.get("y", -1).asInt();

	BaseView* view = makeGridView(base, gridX, gridY);

	// Remove any facilities we're building over (refunding items only; funds are the
	// protocol's job, resolved into the command cost). Mirrors PlaceFacilityState.
	double reducedBuildTime = 0.0;
	bool buildingOver = false;
	const BaseAreaSubset areaToBuildOver = BaseAreaSubset(rule->getSizeX(), rule->getSizeY()).offset(gridX, gridY);
	for (int i = (int)base->getFacilities()->size() - 1; i >= 0; --i)
	{
		BaseFacility* checkFacility = base->getFacilities()->at(i);
		if (!BaseAreaSubset::intersection(areaToBuildOver, checkFacility->getPlacement())) continue;
		const auto& itemCost = checkFacility->getRules()->getBuildCostItems();
		if (checkFacility->getBuildTime() > checkFacility->getRules()->getBuildTime())
		{
			for (auto& item : itemCost)
				base->getStorageItems()->addItem(mod->getItem(item.first, true), item.second.first);
		}
		else
		{
			for (auto& item : itemCost)
				base->getStorageItems()->addItem(mod->getItem(item.first, true), item.second.second);
			double oldSizeSquared = (checkFacility->getRules()->getSizeX() * checkFacility->getRules()->getSizeY());
			double newSizeSquared = (rule->getSizeX() * rule->getSizeY());
			reducedBuildTime += (checkFacility->getRules()->getBuildTime() - checkFacility->getBuildTime()) * oldSizeSquared / newSizeSquared;
			if (checkFacility->getBuildTime() == 0) buildingOver = true;
		}
		if (checkFacility->getAmmo() > 0)
		{
			base->getStorageItems()->addItem(checkFacility->getRules()->getAmmoItem(), checkFacility->getAmmo());
			checkFacility->setAmmo(0);
		}
		base->getFacilities()->erase(base->getFacilities()->begin() + i);
		delete checkFacility;
	}

	BaseFacility* fac = new BaseFacility(rule, base);
	fac->setX(gridX);
	fac->setY(gridY);
	fac->setBuildTime(rule->getBuildTime());
	if (buildingOver)
	{
		fac->setIfHadPreviousFacility(true);
		reducedBuildTime = reducedBuildTime * mod->getBuildTimeReductionScaling() / 100.0;
		int reducedBuildTimeRounded = (int)std::round(reducedBuildTime);
		fac->setBuildTime(std::max(1, fac->getBuildTime() - reducedBuildTimeRounded));
	}
	base->getFacilities()->push_back(fac);
	if (Options::allowBuildingQueue)
	{
		if (view->isQueuedBuilding(rule)) fac->setBuildTime(INT_MAX);
		view->reCalcQueuedBuildings();
	}
	// Debit the build-cost items (funds handled by the protocol).
	for (const auto& item : rule->getBuildCostItems())
		base->getStorageItems()->removeItem(item.first, item.second.first);
	delete view;
}

// fac_dismantle payload: { x, y }. Dismantle the facility at (x,y). If it is the
// access lift (last facility), the whole base is removed - both cases ride
// shared_apply so the base-index stays in lock-step. Refund funds ride the cost.
bool facDismantleValidate(Game* game, const Json::Value& payload, Base* base, int /*seat*/,
                          int64_t& cost, std::string& failReason)
{
	if (!base) { failReason = "base not found"; return false; }
	int x = payload.get("x", -1).asInt();
	int y = payload.get("y", -1).asInt();
	BaseFacility* fac = nullptr;
	for (auto* f : *base->getFacilities())
		if (f->getX() == x && f->getY() == y) { fac = f; break; }
	if (!fac) { failReason = "facility not found"; return false; }

	if (fac->getRules()->isLift())
	{
		// dismantling the access lift removes the whole base; no refund (vanilla).
		cost = 0;
		return true;
	}
	// Re-run the vanilla dismantle-ability guards (BasescapeState checked them before
	// opening the dialog; re-check on the host in case the world changed).
	if (fac->inUse()) { failReason = "STR_FACILITY_IN_USE"; return false; }
	if (!base->getDisconnectedFacilities(fac).empty() && fac->getRules()->getLeavesBehindOnSell().empty())
		{ failReason = "STR_CANNOT_DISMANTLE_FACILITY"; return false; }
	if (fac->getBuildTime() > 0 && fac->getIfHadPreviousFacility())
		{ failReason = "STR_CANNOT_DISMANTLE_FACILITY_UPGRADING"; return false; }

	// Refund (credit): full if a not-yet-started queued build, else partial.
	int64_t refund = (fac->getBuildTime() > fac->getRules()->getBuildTime())
		? fac->getRules()->getBuildCost() : fac->getRules()->getRefundValue();
	cost = -refund; // negative debit = credit; a negative refund becomes an expense
	return true;
}

void facDismantleApply(Game* game, Json::Value& payload, Base* base, int /*seat*/)
{
	if (!base) return;
	Mod* mod = game->getMod();
	SavedGame* save = game->getSavedGame();
	if (!mod || !save) return;
	int x = payload.get("x", -1).asInt();
	int y = payload.get("y", -1).asInt();
	BaseFacility* fac = nullptr;
	for (auto* f : *base->getFacilities())
		if (f->getX() == x && f->getY() == y) { fac = f; break; }
	if (!fac) return;

	if (fac->getRules()->isLift())
	{
		// Remove the whole base (index lock-step: both host and replica erase the
		// same index; subsequent bases shift identically).
		auto* bases = save->getBases();
		for (auto it = bases->begin(); it != bases->end(); ++it)
			if (*it == base) { save->stopHuntingXcomCrafts(base); bases->erase(it); delete base; break; }
		return;
	}

	// Item refund (funds ride the protocol credit): full if queued, else partial.
	const auto& itemCost = fac->getRules()->getBuildCostItems();
	if (fac->getBuildTime() > fac->getRules()->getBuildTime())
		for (auto& pair : itemCost) base->getStorageItems()->addItem(mod->getItem(pair.first, true), pair.second.first);
	else
		for (auto& pair : itemCost) base->getStorageItems()->addItem(mod->getItem(pair.first, true), pair.second.second);
	if (fac->getAmmo() > 0)
	{
		base->getStorageItems()->addItem(fac->getRules()->getAmmoItem(), fac->getAmmo());
		fac->setAmmo(0);
	}

	for (auto facIt = base->getFacilities()->begin(); facIt != base->getFacilities()->end(); ++facIt)
	{
		if (*facIt != fac) continue;
		base->getFacilities()->erase(facIt);
		// Leaves-behind facilities (mods): mirror PlaceFacilityState's rules exactly.
		if (fac->getBuildTime() == 0 && !fac->getRules()->getLeavesBehindOnSell().empty())
		{
			const auto& facList = fac->getRules()->getLeavesBehindOnSell();
			if (facList.at(0)->getSizeX() == fac->getRules()->getSizeX() && facList.at(0)->getSizeY() == fac->getRules()->getSizeY())
			{
				BaseFacility* nf = new BaseFacility(facList.at(0), base);
				nf->setX(fac->getX());
				nf->setY(fac->getY());
				nf->setBuildTime(fac->getRules()->getRemovalTime() <= -1 ? nf->getRules()->getBuildTime() : fac->getRules()->getRemovalTime());
				if (nf->getBuildTime() != 0) nf->setIfHadPreviousFacility(true);
				base->getFacilities()->push_back(nf);
			}
			else
			{
				size_t j = 0;
				for (int ny = fac->getY(); ny != fac->getY() + fac->getRules()->getSizeY(); ++ny)
					for (int nx = fac->getX(); nx != fac->getX() + fac->getRules()->getSizeX(); ++nx)
					{
						BaseFacility* nf = new BaseFacility(facList.at(j), base);
						nf->setX(nx);
						nf->setY(ny);
						nf->setBuildTime(fac->getRules()->getRemovalTime() <= -1 ? nf->getRules()->getBuildTime() : fac->getRules()->getRemovalTime());
						if (nf->getBuildTime() != 0) nf->setIfHadPreviousFacility(true);
						base->getFacilities()->push_back(nf);
						if (++j == facList.size()) j = 0;
					}
			}
		}
		delete fac;
		if (Options::allowBuildingQueue)
		{
			BaseView* view = makeGridView(base, x, y);
			view->reCalcQueuedBuildings();
			delete view;
		}
		break;
	}
}

// base_rename payload: { name }. Replaces the SEPARATE changeBaseName packet in
// SHARED; host applies + broadcasts (last-write-wins).
bool baseRenameValidate(Game* /*game*/, const Json::Value& /*payload*/, Base* base, int /*seat*/,
                        int64_t& cost, std::string& failReason)
{
	if (!base) { failReason = "base not found"; return false; }
	cost = 0;
	return true;
}
void baseRenameApply(Game* /*game*/, Json::Value& payload, Base* base, int /*seat*/)
{
	if (!base) return;
	base->setName(payload.get("name", base->getName()).asString());
}

// sack payload: { soldierId }. Policy: ANY player may sack ANY soldier (shared
// roster management, consistent with J05 sell). No refund (vanilla).
// Separate Campaign: a player acts only on their own soldiers, wherever they are
// stationed (a visitor may sack or rename their own soldier at another player's
// base). SHARED keeps its any-player roster policy.
static bool separateSoldierOwnerOk(Game* game, const Soldier* s, int seat)
{
	if (!game || !game->getSavedGame()
		|| game->getSavedGame()->getCampaignType() != CoopCampaignType::Separate)
		return true;
	return s->getOwnerPlayerId() == seat;
}

bool sackValidate(Game* game, const Json::Value& payload, Base* base, int seat,
                  int64_t& cost, std::string& failReason)
{
	if (!base) { failReason = "base not found"; return false; }
	int id = payload.get("soldierId", -1).asInt();
	for (auto* s : *base->getSoldiers())
		if (s->getId() == id)
		{
			if (!separateSoldierOwnerOk(game, s, seat))
				{ failReason = "STR_COOP_NOT_YOUR_SOLDIER"; return false; }
			cost = 0;
			return true;
		}
	failReason = "soldier not found";
	return false;
}
void sackApply(Game* /*game*/, Json::Value& payload, Base* base, int /*seat*/)
{
	if (!base) return;
	int id = payload.get("soldierId", -1).asInt();
	for (auto it = base->getSoldiers()->begin(); it != base->getSoldiers()->end(); ++it)
	{
		Soldier* s = *it;
		if (s->getId() != id) continue;
		if (s->getArmor()->getStoreItem())
			base->getStorageItems()->addItem(s->getArmor()->getStoreItem());
		base->getSoldiers()->erase(it);
		delete s;
		break;
	}
}

// ---- soldier_transform { rule, soldierId, dead, name } ------------------------------
// Player-origin; own soldiers only; vanilla's list / Start gates re-checked on the host; cost = the rule's cost.
// HOST: vanilla's stores loop + its own retire() / performTransformation() on a never-pushed screen (the dice roll
// once, here); the result rides the payload: out (retire | clone | self), hours (0 = no Transfer), soldier, history
// and soldierCounter (clone), stores, craft (the source's former craft). The clone is the seat's. REPLICA: adopts.
Soldier* findTransformSource(Game* game, Base* base, const Json::Value& payload)
{
	int id = payload.get("soldierId", -1).asInt();
	if (!payload.get("dead", false).asBool()) return findSoldier(base, id);
	for (auto* s : *game->getSavedGame()->getDeadSoldiers())
		if (s->getId() == id) return s;
	return nullptr;
}

bool soldierTransformValidate(Game* game, const Json::Value& payload, Base* base, int seat,
                              int64_t& cost, std::string& failReason)
{
	cost = 0;
	if (!base) { failReason = "base not found"; return false; }
	SavedGame* save = game->getSavedGame();
	Mod* mod = game->getMod();
	RuleSoldierTransformation* rule = mod->getSoldierTransformation(payload.get("rule", "").asString(), false);
	if (!rule) { failReason = "unknown transformation"; return false; }
	std::vector<RuleSoldierTransformation*> available;
	save->getAvailableTransformations(available, mod, base);
	if (std::find(available.begin(), available.end(), rule) == available.end())
		{ failReason = "transformation not available"; return false; }
	Soldier* s = findTransformSource(game, base, payload);
	if (!s) { failReason = "soldier not found"; return false; }
	if (!separateSoldierOwnerOk(game, s, seat))
		{ failReason = "STR_COOP_NOT_YOUR_SOLDIER"; return false; }
	if (game->getSavedGame()->getCampaignType() != CoopCampaignType::Separate && s->getOwnerPlayerId() != seat)
		{ failReason = "not your soldier"; return false; } // own soldiers only
	// vanilla's gates: SoldiersState :458-463 (list), SoldierTransformationState::initTransformationData :191-232 (Start button)
	if (s->getCraft() && s->getCraft()->getStatus() == "STR_OUT") { failReason = "craft out on mission"; return false; }
	s->prepareStatsWithBonuses(mod);
	if (!s->isEligibleForTransformation(rule)) { failReason = "soldier not eligible"; return false; }
	if (save->getFunds() < rule->getCost()) { failReason = "STR_NOT_ENOUGH_MONEY"; return false; }
	for (const auto& ri : rule->getRequiredItems())
	{
		const RuleItem* item = mod->getItem(ri.first);
		if (item && base->getStorageItems()->getItem(item) < ri.second)
			{ failReason = "not enough items"; return false; }
	}
	if (base->getAvailableQuarters() <= base->getUsedQuarters()
		&& (rule->isCreatingClone() || (rule->isAllowingDeadSoldiers() && s->getDeath())))
		{ failReason = "STR_NOT_ENOUGH_LIVING_SPACE"; return false; }
	cost = rule->getCost();
	return true;
}

void soldierTransformApply(Game* game, Json::Value& payload, Base* base, int seat)
{
	if (!base) return;
	SavedGame* save = game->getSavedGame();
	Mod* mod = game->getMod();
	RuleSoldierTransformation* rule = mod->getSoldierTransformation(payload.get("rule", "").asString(), false);
	Soldier* src = findTransformSource(game, base, payload);
	if (!rule || !src) return;
	const bool retiring = !Mod::isEmptyRuleName(rule->getProducedItem());
	const std::string transferOwner = connectionTCP::seatName(seat);
	if (connectionTCP::getHost())
	{
		// HOST: vanilla's btnStartClick minus the funds (debited by the caller) and the pop
		Craft* oldCraft = src->getCraft();
		size_t nT = base->getTransfers()->size();
		for (auto& ri : rule->getRequiredItems())
			if (const auto* item = mod->getItem(ri.first))
				base->getStorageItems()->removeItem(item, ri.second);
		{
			SoldierTransformationState vanilla(rule, base, src, nullptr); // never pushed
			if (retiring) vanilla.retire(); // deletes src: never touched after this
			else vanilla.performTransformation();
		}
		Transfer* t = base->getTransfers()->size() > nT ? base->getTransfers()->back() : nullptr;
		if (t) t->setOwnerPlayerName(transferOwner);
		payload["hours"] = t ? t->getHours() : 0;
		payload["out"] = retiring ? "retire" : rule->isCreatingClone() ? "clone" : "self";
		if (!retiring)
		{
			Soldier* dst = rule->isCreatingClone() && t ? t->getSoldier() : src;
			dst->setName(payload.get("name", dst->getName()).asString()); // the screen's name box
			if (rule->isCreatingClone())
			{
				dst->setOwnerPlayerId(seat);
				payload["history"] = Json::Value(Json::objectValue);
				for (const auto& kv : src->getPreviousTransformations()) payload["history"][kv.first] = kv.second;
				const auto& ids = save->getAllIds();
				payload["soldierCounter"] = ids.find("STR_SOLDIER") != ids.end() ? ids.at("STR_SOLDIER") : 0;
			}
			payload["soldier"] = serializeSoldier(game, dst);
		}
		payload["stores"] = Json::Value(Json::objectValue);
		for (const auto& kv : *base->getStorageItems()->getContents())
			payload["stores"][kv.first->getType()] = kv.second;
		if (oldCraft)
		{
			payload["craft"]["id"] = oldCraft->getId();
			payload["craft"]["type"] = oldCraft->getRules()->getType();
			payload["craft"]["items"] = Json::Value(Json::objectValue);
			for (const auto& kv : *oldCraft->getItems()->getContents())
				payload["craft"]["items"][kv.first->getType()] = kv.second;
		}
		return;
	}

	// Replica: adopt the host's result; never roll and never run the transformation.
	const std::string out = payload.get("out", "").asString();
	const int hours = payload.get("hours", 0).asInt();
	std::vector<Soldier*>* home = payload.get("dead", false).asBool() ? save->getDeadSoldiers() : base->getSoldiers();
	auto it = std::find(home->begin(), home->end(), src);
	auto push = [&](Transfer* t) { t->setOwnerPlayerName(transferOwner); base->getTransfers()->push_back(t); return t; };
	if (out == "retire")
	{
		if (it != home->end()) home->erase(it);
		delete src;
		push(new Transfer(hours))->setItems(mod->getItem(rule->getProducedItem(), true), 1);
	}
	else if (out == "clone")
	{
		src->setCraft(0); // vanilla unseats the source; its kit rides stores / craft below
		std::map<std::string, int>& hist = src->getPreviousTransformations();
		hist.clear();
		for (const auto& k : payload["history"].getMemberNames()) hist[k] = payload["history"][k].asInt();
		if (Soldier* c = deserializeSoldier(game, payload.get("soldier", "").asString()))
			push(new Transfer(hours))->setSoldier(c);
		const int want = payload.get("soldierCounter", 0).asInt(); // keep the id counter in step
		const auto& ids = save->getAllIds();
		while (ids.find("STR_SOLDIER") == ids.end() || ids.at("STR_SOLDIER") < want) save->getId("STR_SOLDIER");
	}
	else if (out == "self")
	{
		Soldier* d = deserializeSoldier(game, payload.get("soldier", "").asString());
		if (!d) return;
		if (hours > 0)
		{
			if (it != home->end()) home->erase(it);
			delete src;
			push(new Transfer(hours))->setSoldier(d);
		}
		else if (it != home->end()) { *it = d; delete src; } // same roster place; unseated like the host's
		else delete d;
	}
	auto setItems = [&](ItemContainer* ic, const Json::Value& items)
	{
		ic->clear();
		for (const auto& k : items.getMemberNames())
			if (RuleItem* ri = mod->getItem(k, false)) ic->addItem(ri, items[k].asInt());
	};
	setItems(base->getStorageItems(), payload["stores"]);
	if (payload.isMember("craft"))
		if (Craft* cr = findCraft(base, payload["craft"].get("id", -1).asInt(), payload["craft"].get("type", "").asString()))
			setItems(cr->getItems(), payload["craft"]["items"]);
}

// soldier_rename payload: { soldierId, name }. Playtest B3: soldier renames were
// local-only; in SHARED they ride the shared_cmd like base_rename (host applies +
// broadcasts, last-write-wins). ANY player may rename ANY soldier (shared roster,
// consistent with sack). The soldier is looked up by id at the command's base.
bool soldierRenameValidate(Game* game, const Json::Value& payload, Base* base, int seat,
                           int64_t& cost, std::string& failReason)
{
	if (!base) { failReason = "base not found"; return false; }
	int id = payload.get("soldierId", -1).asInt();
	for (auto* s : *base->getSoldiers())
		if (s->getId() == id)
		{
			if (!separateSoldierOwnerOk(game, s, seat))
				{ failReason = "STR_COOP_NOT_YOUR_SOLDIER"; return false; }
			cost = 0;
			return true;
		}
	failReason = "soldier not found";
	return false;
}
void baseEquipMarkName(Soldier* s); // defined after soldierEquipApply
void soldierRenameApply(Game* /*game*/, Json::Value& payload, Base* base, int /*seat*/)
{
	if (!base) return;
	int id = payload.get("soldierId", -1).asInt();
	for (auto* s : *base->getSoldiers())
		if (s->getId() == id) { s->setName(payload.get("name", s->getName()).asString()); break; }
	baseEquipMarkName(findSoldier(base, id)); // an open base screen's mark keeps this rename (no put-back at its OK)
}

// soldier_gift payload: { soldierId, newOwner }. Playtest: gifting (give-unit) a
// soldier to the other player must be host-authoritative in SHARED (the SEPARATE
// local+broadcast path never reached the SHARED replica). Host validates + sets the
// owner, broadcasts shared_apply; replicas adopt. Ownership move only - the soldier
// stays in the one shared roster.
bool soldierGiftValidate(Game* /*game*/, const Json::Value& payload, Base* base, int /*seat*/,
                         int64_t& cost, std::string& failReason)
{
	if (!base) { failReason = "base not found"; return false; }
	int id = payload.get("soldierId", -1).asInt();
	for (auto* s : *base->getSoldiers())
		if (s->getId() == id) { cost = 0; return true; }
	failReason = "soldier not found";
	return false;
}
void soldierGiftApply(Game* game, Json::Value& payload, Base* base, int /*seat*/)
{
	if (!base) return;
	int id = payload.get("soldierId", -1).asInt();
	int newOwner = payload.get("newOwner", 0).asInt();
	for (auto* s : *base->getSoldiers())
		if (s->getId() == id)
		{
			const int previousOwner = s->getOwnerPlayerId();
			s->setOwnerPlayerId(newOwner);
			s->setCoop(newOwner);
			// Separate: tell the receiving player about the gift.
			// SHARED shows no notice.
			if (game && game->getCoopMod() && game->getCoopMod()->isSeparateCampaign()
				&& previousOwner != newOwner && newOwner == connectionTCP::localSeat())
			{
				game->pushState(new GiftNoticeState(game->getCoopMod()->getCurrentClientName()
					+ " gifted " + s->getName() + " to you at base " + base->getName()));
			}
			break;
		}
}

// base_new payload: { lon, lat, name, liftType, liftX, liftY } (+ host-resolved
// coopbaseid). Client-originated creation of a SUBSEQUENT base (the initial
// campaign base is J02's, host-side pre-stream). baseId is -1 (no existing base);
// the applier appends the new base at the SAME index on host and every replica so
// the index stays in lock-step. Host debits the region base cost once.
bool baseNewValidate(Game* game, const Json::Value& payload, Base* /*base*/, int /*seat*/,
                     int64_t& cost, std::string& failReason)
{
	SavedGame* save = game->getSavedGame();
	Mod* mod = game->getMod();
	if (!save || !mod) { failReason = "no world"; return false; }
	// The eight-base limit is campaign-wide in both co-op campaign types.  It
	// must not scale with the number of seats.
	if (save->getBases()->size() >= 8) { failReason = "STR_MAXIMUM_NUMBER_OF_BASES_REACHED"; return false; }
	double lon = payload.get("lon", 0.0).asDouble();
	double lat = payload.get("lat", 0.0).asDouble();
	int regionCost = -1;
	for (const auto* region : *save->getRegions())
		if (region->getRules()->insideRegion(lon, lat)) { regionCost = region->getRules()->getBaseCost(); break; }
	if (regionCost < 0) { failReason = "no region for base"; return false; }
	if (!mod->getBaseFacility(payload.get("liftType", "").asString(), false))
		{ failReason = "unknown access lift"; return false; }
	if (save->getFunds() < regionCost) { failReason = "STR_NOT_ENOUGH_MONEY"; return false; }
	cost = regionCost;
	return true;
}

void baseNewApply(Game* game, Json::Value& payload, Base* /*base*/, int seat)
{
	SavedGame* save = game->getSavedGame();
	Mod* mod = game->getMod();
	if (!save || !mod) return;

	Base* nb = new Base(mod); // ctor random-mints _coop_base_id
	std::string ownerName = payload.get("ownerPlayerName", connectionTCP::seatName(seat)).asString();
	nb->setOwnerPlayerName(ownerName);
	if (save->isSeparateCoopCampaign())
		nb->_isForeignBase = !nb->isOwnedByPlayer(connectionTCP::seatName(connectionTCP::localSeat()));
	nb->setFakeUnderwater(payload.get("fakeUnderwater", false).asBool());
	nb->setLongitude(payload.get("lon", 0.0).asDouble());
	nb->setLatitude(payload.get("lat", 0.0).asDouble());
	nb->setName(payload.get("name", "").asString());
	nb->calculateServices(save);

	// coopbaseid: host mints (already done by the ctor); serialize into the payload
	// so replicas adopt the SAME id (the buy-soldier host-RNG-into-payload pattern).
	if (connectionTCP::getHost() && !payload.isMember("coopbaseid"))
		payload["coopbaseid"] = nb->_coop_base_id;
	else if (payload.isMember("coopbaseid"))
		nb->_coop_base_id = payload["coopbaseid"].asInt();

	RuleBaseFacility* liftRule = mod->getBaseFacility(payload.get("liftType", "").asString(), false);
	if (liftRule)
	{
		BaseFacility* lift = new BaseFacility(liftRule, nb); // default buildTime 0 = instant
		lift->setX(payload.get("liftX", 0).asInt());
		lift->setY(payload.get("liftY", 0).asInt());
		nb->getFacilities()->push_back(lift);
	}
	nb->calculateServices(save);
	save->getBases()->push_back(nb);
}

// base_destroyed payload: { name } (baseId = index of the destroyed base). Host
// simulates retaliation (J04) and removes the base in BaseDestroyedState; this
// mirrors the removal to replicas (applier runs REPLICA-ONLY: the host already
// erased the base) and pops an informational popup.
void baseDestroyedApply(Game* game, Json::Value& payload, Base* base, int /*seat*/)
{
	if (connectionTCP::getHost()) return; // host already removed it in BaseDestroyedState
	g_sel.clear(); // base indices shift - every binder re-keys on its next think()
	if (!base) return;
	SavedGame* save = game->getSavedGame();
	if (!save) return;
	std::string name = payload.get("name", base->getName()).asString();
	// coop: the geoscape windows that hold this
	// base or one of its crafts (a craft's window, the INTERCEPT list, a destination pick, list or confirm, a patrol, dogfight, landing,
	// Cydonia or pilots notice) close first, as their CANCEL does (coopCloseMirrorHolders); the base is deleted either way.
	std::vector<Target*> doomedTargets{ base };
	for (Craft* doomedCraft : *base->getCrafts())
		doomedTargets.push_back(doomedCraft);
	coopCloseMirrorHolders(game, doomedTargets);
	auto* bases = save->getBases();
	for (auto it = bases->begin(); it != bases->end(); ++it)
		if (*it == base) { save->stopHuntingXcomCrafts(base); bases->erase(it); delete base; break; }
	// Match the host's wording: an alien MISSILE strike reads differently from an
	// undefended base being overrun. (The base is erased immediately rather than when
	// the player dismisses a dialog, so that every machine drops the same base INDEX at
	// the same moment - baseId is the protocol's routing key - which is why this is a
	// message rather than the full BaseDestroyedState dialog.)
	const std::string msgKey = payload.get("missiles", false).asBool()
		? "STR_ALIEN_MISSILES_HAVE_DESTROYED_OUR_BASE"
		: "STR_THE_ALIENS_HAVE_DESTROYED_THE_UNDEFENDED_BASE";
	auto* itf = game->getMod()->getInterface("geoscape");
	game->pushState(new ErrorMessageState(
		game->getLanguage()->getString(msgKey).arg(name),
		game->getScreen()->getPalette(),
		itf->getElement("genericWindow")->color, "BACK01.SCR", itf->getElement("palette")->color));
}

// ---- PRD-J04: host simulation-result commands --------------------------------
// These mirror a host-only completion to replicas. The host has ALREADY applied
// the change via vanilla sim, so:
//   validator : always accept, cost 0 (funds stay host-authoritative; the packet
//               carries getFunds() so replicas re-sync funds for free).
//   applier   : runs on the REPLICA only (early-returns on the host) to avoid a
//               double-apply.

// Locate the live GeoscapeState (for completion popups that need it). Null if the
// replica is currently in a sub-screen/battle -> we simply skip the popup then.
GeoscapeState* findGeoState(Game* game)
{
	if (!game) return nullptr;
	for (auto* st : game->getStates())
	{
		if (auto* gs = dynamic_cast<GeoscapeState*>(st)) return gs;
	}
	return nullptr;
}

// The soldier state the host's day and month steps write: wound recovery and
// missing health/mana (replenishStats), martial and psi training (stats, the
// training flags, the psi improvement scores) and the dogfight-XP reset. The
// host snapshots it before the step (hostSoldierStepBegin) and day_tick carries
// every soldier whose state changed, so the replica holds the host's values
// right after the step instead of waiting for a checksum restream.
struct SoldierStepState
{
	int id = -1;
	int owner = -1;
	float recovery = 0.0f;
	int healthMissing = 0;
	int manaMissing = 0;
	UnitStats stats;
	UnitStats dogfight;
	bool training = false;
	bool psiTraining = false;
	bool trainingQueued = false;
	int improvement = 0;
	int psiStrImprovement = 0;
};

SoldierStepState soldierStepState(Soldier* s)
{
	SoldierStepState st;
	st.id = s->getId();
	st.owner = s->getOwnerPlayerId();
	st.recovery = s->getWoundRecoveryExact();
	st.healthMissing = s->getHealthMissing();
	st.manaMissing = s->getManaMissing();
	st.stats = *s->getCurrentStats();
	st.dogfight = *s->getDailyDogfightExperienceCache();
	st.training = s->isInTraining();
	st.psiTraining = s->isInPsiTraining();
	st.trainingQueued = s->getReturnToTrainingWhenHealed();
	st.improvement = s->getImprovement();
	st.psiStrImprovement = s->getPsiStrImprovement();
	return st;
}

bool sameUnitStats(const UnitStats& a, const UnitStats& b)
{
	bool same = true;
	UnitStats::fieldLoop([&](UnitStats::Ptr field) { if (a.*field != b.*field) same = false; });
	return same;
}

bool sameStepState(const SoldierStepState& a, const SoldierStepState& b)
{
	return a.id == b.id && a.owner == b.owner && a.recovery == b.recovery
		&& a.healthMissing == b.healthMissing && a.manaMissing == b.manaMissing
		&& sameUnitStats(a.stats, b.stats) && sameUnitStats(a.dogfight, b.dogfight)
		&& a.training == b.training && a.psiTraining == b.psiTraining
		&& a.trainingQueued == b.trainingQueued && a.improvement == b.improvement
		&& a.psiStrImprovement == b.psiStrImprovement;
}

Json::Value unitStatsJson(const UnitStats& st)
{
	Json::Value arr(Json::arrayValue);
	UnitStats::fieldLoop([&](UnitStats::Ptr field) { arr.append((int)(st.*field)); });
	return arr;
}

void readUnitStats(const Json::Value& arr, UnitStats& out)
{
	if (!arr.isArray() || arr.size() == 0) return;
	Json::ArrayIndex i = 0;
	UnitStats::fieldLoop([&](UnitStats::Ptr field)
	{
		if (i < arr.size()) out.*field = (UnitStats::Type)arr[i].asInt();
		++i;
	});
}

// day_tick soldier entry: the soldier's id and owner (ids may repeat across
// players) and its complete step state, stats in UnitStats::fieldLoop order.
Json::Value soldierStepJson(const SoldierStepState& st)
{
	Json::Value js;
	js["id"] = st.id;
	js["owner"] = st.owner;
	js["recovery"] = (double)st.recovery;
	js["healthMissing"] = st.healthMissing;
	js["manaMissing"] = st.manaMissing;
	js["stats"] = unitStatsJson(st.stats);
	js["dogfight"] = unitStatsJson(st.dogfight);
	js["training"] = st.training;
	js["psiTraining"] = st.psiTraining;
	js["trainingQueued"] = st.trainingQueued;
	js["improvement"] = st.improvement;
	js["psiStrImprovement"] = st.psiStrImprovement;
	return js;
}

// The snapshot taken before the step, per soldier object. Armed by
// hostSoldierStepBegin, consumed (and cleared) by hostDayTick.
std::map<const Soldier*, SoldierStepState> g_soldierStepBefore;
const SavedGame* g_soldierStepSave = nullptr;
bool g_soldierStepArmed = false;

bool simAccept(Game* /*game*/, const Json::Value& /*payload*/, Base* /*base*/,
               int /*seat*/, int64_t& cost, std::string& /*failReason*/)
{
	cost = 0; // host-authoritative funds unchanged; broadcast carries getFunds()
	return true;
}

// ---- PRD-J08: shared craft command + dogfight coordination --------------------
// Any player commands any craft. Orders are shared_cmds; the host validates the
// vanilla fuel/crew/status rules against the authoritative world and applies in
// ARRIVAL order (last-command-wins - a later order for the same craft simply
// overrides the destination; no locking). Craft identity across machines =
// rule type + per-type id (the proven findCraft identity).

std::string craftKey(const std::string& type, int id)
{
	return type + "#" + std::to_string(id);
}
std::string craftKey(const Craft* c)
{
	return craftKey(c->getRules()->getType(), c->getId());
}

// Seat of the last APPLIED order per craft. Host and every replica record it
// from the same shared_apply stream, so it is identical everywhere. The host
// routes dogfights by it (the initiating seat flies). -1 / absent = the craft
// was never commanded through the protocol -> treat as host-owned (vanilla).
std::map<std::string, int> g_craftOrderSeat;

// Resolve the ordered craft: prefer the command's base, fall back to a
// world-wide search (the craft may have been transferred since the order).
Craft* resolveOrderCraft(Game* game, const Json::Value& p, Base* base)
{
	int id = p.get("craftId", -1).asInt();
	std::string type = p.get("craftType", "").asString();
	if (base)
		if (Craft* c = findCraft(base, id, type)) return c;
	SavedGame* save = game->getSavedGame();
	if (save)
		for (auto* b : *save->getBases())
			if (Craft* c = findCraft(b, id, type)) return c;
	return nullptr;
}

// Resolve the order's target on THIS machine's world (real shared ids). Null
// for targetType "point" (the applier creates the shared waypoint) or when the
// id does not resolve here (replica snapshot race - harmless, see applier).
Target* resolveOrderTarget(Game* game, const Json::Value& p)
{
	SavedGame* save = game->getSavedGame();
	if (!save) return nullptr;
	std::string tt = p.get("targetType", "").asString();
	int tid = p.get("targetId", -1).asInt();
	if (tt == "ufo")
	{
		for (auto* u : *save->getUfos()) if (u->getId() == tid) return u;
	}
	else if (tt == "site")
	{
		for (auto* s : *save->getMissionSites()) if (s->getId() == tid) return s;
	}
	else if (tt == "abase")
	{
		for (auto* b : *save->getAlienBases()) if (b->getId() == tid) return b;
	}
	else if (tt == "xbase")
	{
		return resolveBase(game, p.get("tBaseId", -1).asInt());
	}
	else if (tt == "xcraft")
	{
		Base* b = resolveBase(game, p.get("tBaseId", -1).asInt());
		if (b) return findCraft(b, p.get("tCraftId", -1).asInt(), p.get("tCraftType", "").asString());
	}
	return nullptr;
}

// craft_launch / craft_retarget payload: { craftId, craftType, targetType:
// "ufo"|"site"|"abase"|"xbase"|"xcraft"|"point", targetId | tBaseId(+tCraftId,
// tCraftType), lon, lat }. baseId = the craft's home-base index. The two cmds
// share semantics (set destination); the distinct names keep intent readable.
bool craftOrderValidate(Game* game, const Json::Value& payload, Base* base, int /*seat*/,
                        int64_t& cost, std::string& failReason)
{
	Craft* craft = resolveOrderCraft(game, payload, base);
	if (!craft) { failReason = "craft not found"; return false; }
	// vanilla launch/redirect gate (InterceptState::lstCraftsLeftClick allowStart).
	const std::string status = craft->getStatus();
	bool allow = status == "STR_READY"
		|| ((status == "STR_OUT" || Options::craftLaunchAlways)
			&& !craft->getLowFuel() && !craft->getMissionComplete());
	if (!allow) { failReason = "craft not ready"; return false; }
	// vanilla crew gate (ConfirmDestinationState::btnOkClick).
	if (!craft->arePilotsOnboard(game->getMod())) { failReason = "STR_PILOT_MISSING"; return false; }
	std::string tt = payload.get("targetType", "").asString();
	if (tt != "point" && !resolveOrderTarget(game, payload))
		{ failReason = "target not found"; return false; }
	cost = 0;
	return true;
}

// issue #78: prune waypoints nobody follows any more. The vanilla sweep lives
// in GeoscapeState::timeAdvance, which never runs on a SHARED replica - so the
// craft-order appliers call this on BOTH machines right after changing a
// destination, keeping the marker set converged the moment the order lands.
static void sweepOrphanWaypoints(SavedGame* save)
{
	if (!save) return;
	auto* ways = save->getWaypoints();
	for (auto it = ways->begin(); it != ways->end(); )
	{
		if ((*it)->getFollowers()->empty())
		{
			delete *it;
			it = ways->erase(it);
		}
		else
		{
			++it;
		}
	}
}

void craftOrderApply(Game* game, Json::Value& payload, Base* base, int seat)
{
	SavedGame* save = game->getSavedGame();
	if (!save) return;
	Craft* craft = resolveOrderCraft(game, payload, base);
	if (!craft) return;
	g_craftOrderSeat[craftKey(craft)] = seat; // initiating seat (dogfight routing)
	// the launch check's automatic pilots (craftOrderValidate's arePilotsOnboard) reach the replica too
	if (craft->getRules()->getPilots() > 0)
	{
		if (connectionTCP::getHost())
		{
			Json::Value ids(Json::arrayValue);
			for (auto* p : craft->getPilotList(true, game->getMod())) ids.append(p->getId());
			payload["pilots"] = ids;
		}
		else if (payload.isMember("pilots"))
		{
			craft->removeAllPilots();
			for (const auto& id : payload["pilots"]) craft->addPilot(id.asInt());
		}
	}

	std::string tt = payload.get("targetType", "").asString();
	Target* target = nullptr;
	bool resolved = false;
	if (tt == "point")
	{
		// A shared waypoint, created by this applier on the host AND every
		// replica, so the STR_WAY_POINT id counter stays in lock-step.
		Waypoint* w = new Waypoint();
		w->setLongitude(payload.get("lon", 0.0).asDouble());
		w->setLatitude(payload.get("lat", 0.0).asDouble());
		w->setId(save->getId("STR_WAY_POINT"));
		save->getWaypoints()->push_back(w);
		target = w;
		resolved = true;
	}
	else
	{
		target = resolveOrderTarget(game, payload);
		resolved = (target != nullptr);
	}
	if (resolved)
	{
		if (target == craft) target = nullptr; // vanilla: self-target = "patrol here"
		craft->setDestination(target);
	}
	// else: a replica that has not yet seen the target via the position
	// snapshot. Skip the local _dest label; position/status still track the
	// host through the snapshot, and dogfight_start re-asserts _dest if needed.
	if (craft->getRules()->canAutoPatrol())
		craft->setIsAutoPatrolling(false); // vanilla: a new order cancels auto-patrol
	craft->setStatus("STR_OUT");
	sweepOrphanWaypoints(save); // issue #78: the retargeted-away waypoint dies NOW
}

// craft_return / craft_patrol payload: { craftId, craftType } (+ patrol:
// { auto:bool } - true from the geoscape craft dialog, which starts
// auto-patrol on capable craft; false from the "self-target" confirm path).
bool craftExistsValidate(Game* game, const Json::Value& payload, Base* base, int /*seat*/,
                         int64_t& cost, std::string& failReason)
{
	if (!resolveOrderCraft(game, payload, base)) { failReason = "craft not found"; return false; }
	cost = 0;
	return true;
}

void craftReturnApply(Game* game, Json::Value& payload, Base* base, int seat)
{
	Craft* craft = resolveOrderCraft(game, payload, base);
	if (!craft) return;
	g_craftOrderSeat[craftKey(craft)] = seat;
	craft->returnToBase();
	if (craft->getRules()->canAutoPatrol())
		craft->setIsAutoPatrolling(false); // vanilla GeoscapeCraftState::btnBaseClick
	sweepOrphanWaypoints(game->getSavedGame()); // issue #78
}

void craftPatrolApply(Game* game, Json::Value& payload, Base* base, int seat)
{
	Craft* craft = resolveOrderCraft(game, payload, base);
	if (!craft) return;
	g_craftOrderSeat[craftKey(craft)] = seat;
	craft->setDestination(0);
	if (payload.get("auto", false).asBool() && craft->getRules()->canAutoPatrol())
	{
		// vanilla GeoscapeCraftState::btnPatrolClick auto-patrol anchor.
		craft->setLatitudeAuto(craft->getLatitude());
		craft->setLongitudeAuto(craft->getLongitude());
		craft->setIsAutoPatrolling(true);
	}
	sweepOrphanWaypoints(game->getSavedGame()); // issue #78
}

// ---- PRD-J09: shared-world squad assembly -----------------------------------
// In SHARED there is ONE base/craft/roster shared by both players, so assigning
// or removing a soldier to/from a craft is a shared-world mutation and rides the
// protocol (never mutated locally on a replica). payload:
//   { craftId, craftType, soldierId, onOff }   baseId = the craft's home-base
// index (the soldier lives at the same base). onOff = the DESIRED final state
// (true = aboard this craft, false = off it) so host and replica converge
// regardless of arrival order (last-write-wins, like the craft orders). Vehicles
// are covered by the same craft space accounting (getSpaceAvailable counts unit
// size); a dedicated vehicle assign command was not needed for the AC.
Soldier* findSoldierAtBase(Base* base, int id, int owner = -1)
{
	if (!base) return nullptr;
	for (auto* s : *base->getSoldiers())
		if (s->getId() == id && (owner < 0 || s->getOwnerPlayerId() == owner)) return s;
	return nullptr;
}

bool craftAssignValidate(Game* game, const Json::Value& payload, Base* base, int seat,
                         int64_t& cost, std::string& failReason)
{
	if (game && game->getSavedGame()
		&& game->getSavedGame()->isSeparateCoopCampaign())
		return SeparateEcon::validateCraftAssign(
			game, payload, base, seat, cost, failReason);

	cost = 0; // no funds effect; broadcast still carries authoritative getFunds()
	if (!base) { failReason = "base not found"; return false; }
	Craft* craft = resolveOrderCraft(game, payload, base);
	if (!craft) { failReason = "craft not found"; return false; }
	Soldier* s = findSoldierAtBase(base, payload.get("soldierId", -1).asInt(),
		payload.get("soldierOwner", -1).asInt());
	if (!s) { failReason = "soldier not found"; return false; }
	const bool onOff = payload.get("onOff", false).asBool();
	// A craft already OUT on a mission is locked (vanilla lstSoldiersClick).
	if (s->getCraft() && s->getCraft()->getStatus() == "STR_OUT")
		{ failReason = "craft out on mission"; return false; }
	if (onOff && s->getCraft() != craft)
	{
		// vanilla CraftSoldiersState::lstSoldiersClick add gates.
		if (!s->hasFullHealth()) { failReason = "STR_SOLDIER_NOT_APPROVED"; return false; }
		int space = craft->getSpaceAvailable();
		CraftPlacementErrors err = craft->validateAddingSoldier(space, s);
		if (err != CPE_None) { failReason = "STR_NOT_ENOUGH_CRAFT_SPACE"; return false; }
	}
	return true;
}

void craftAssignApply(Game* game, Json::Value& payload, Base* base, int /*seat*/)
{
	if (!base) return;
	Craft* craft = resolveOrderCraft(game, payload, base);
	Soldier* s = findSoldierAtBase(base, payload.get("soldierId", -1).asInt(),
		payload.get("soldierOwner", -1).asInt());
	if (!craft || !s) return;
	const bool onOff = payload.get("onOff", false).asBool();
	const bool newBattle = game->getSavedGame()->getMonthsPassed() == -1;
	if (onOff)
		s->setCraftAndMoveEquipment(craft, base, newBattle, true);
	else if (s->getCraft() == craft)
		s->setCraftAndMoveEquipment(0, base, newBattle);
}

// ---- craft pilot picks ----------------------------------------------------------------
// craft_pilots { craftId, craftType, op: "add" | "clear", soldierId (add) }, baseId = the craft's home base. Player-origin
// from either seat. The host applies vanilla's rules to its own world (add: a free seat for a crew soldier able to fly, else
// kept silently; clear: the seat's own pilots go, the partner's stay) and writes the resolved list as "pilots".
bool craftPilotsValidate(Game* game, const Json::Value& payload, Base* base, int seat,
                         int64_t& cost, std::string& failReason)
{
	cost = 0;
	if (!base) { failReason = "base not found"; return false; }
	if (!resolveOrderCraft(game, payload, base)) { failReason = "craft not found"; return false; }
	const std::string op = payload.get("op", "").asString();
	if (op == "clear") return true;
	if (op != "add") { failReason = "unknown pilot order"; return false; }
	Soldier* s = findSoldier(base, payload.get("soldierId", -1).asInt());
	if (!s) { failReason = "soldier not found"; return false; }
	if (s->getOwnerPlayerId() != seat) { failReason = "not your soldier"; return false; } // own soldiers only
	return true;
}
void craftPilotsApply(Game* game, Json::Value& payload, Base* base, int seat)
{
	if (!base) return;
	Craft* craft = resolveOrderCraft(game, payload, base);
	if (!craft) return;
	if (connectionTCP::getHost())
	{
		// vanilla's manual list, as the pilots screen shows it (CraftPilotsState :165)
		std::vector<Soldier*> list = craft->getPilotList(false, game->getMod());
		if (payload.get("op", "").asString() == "clear")
		{
			craft->removeAllPilots();
			for (auto* p : list)
				if (p->getOwnerPlayerId() != seat) craft->addPilot(p->getId()); // the partner's picks stay
		}
		else
		{
			Soldier* s = findSoldier(base, payload.get("soldierId", -1).asInt());
			// vanilla's gates: the select screen offers crew able to fly (CraftPilotSelectState :99); Add shows only
			// while a seat is free (CraftPilotsState :209)
			if (s && s->getCraft() == craft && s->hasAllPilotingRequirements()
				&& (int)list.size() < craft->getRules()->getPilots())
				craft->addPilot(s->getId());
		}
		Json::Value ids(Json::arrayValue);
		for (auto* p : craft->getPilotList(false, game->getMod())) ids.append(p->getId());
		payload["pilots"] = ids; // the resolved list rides the broadcast
	}
	else
	{
		craft->removeAllPilots();
		for (const auto& id : payload["pilots"]) craft->addPilot(id.asInt());
	}
}

// ---- PRD-J09 GAP-5: shared-world craft equipment loadout ---------------------
// Equipping a craft at the BASE screen (CraftEquipmentState) moves items between
// the shared base stores and the craft. Those base stores are host-authoritative
// (they are exactly what the GAP-4 checksum sums), so a replica must never mutate
// them locally - it routes the move through this command instead. payload:
//   { craftId, craftType, item, count }   baseId = the craft's home-base index.
// count = the ABSOLUTE desired quantity of `item` loaded on the craft, so host
// and replica converge regardless of arrival order (the J08/J09 last-write-wins
// idiom). A vehicle item (an HWP) counts whole vehicles with their clip ammo (craftEquipVehicles);
// CraftEquipmentState routes an item move before vanilla's and an HWP move's end-state right after it.
// Separate Campaign vehicles share this command envelope, but their ownership and
// seat-priority rules live in SeparateEcon.
bool craftEquipValidate(Game* game, const Json::Value& payload, Base* base, int seat,
                        int64_t& cost, std::string& failReason)
{
	cost = 0; // no funds effect; broadcast still carries authoritative getFunds()
	if (!base) { failReason = "base not found"; return false; }
	if (!resolveOrderCraft(game, payload, base)) { failReason = "craft not found"; return false; }
	if (game->getSavedGame()->isSeparateCoopCampaign())
		return SeparateEcon::validateCraftEquip(
			game, payload, base, seat, cost, failReason);
	const RuleItem* item = game->getMod()->getItem(payload.get("item", "").asString(), false);
	if (!item) { failReason = "unknown item"; return false; }
	return true;
}

// the HWP branch of craft_equip. `count` = the ABSOLUTE number of vehicles of type `item` on the craft, resolved
// with vanilla's CraftEquipmentState rules (moveRightByValue / moveLeftByValue): a vehicle leaves the stores with its clip ammo while the
// craft has room and enters with full ammo (each one resets a custom craft deployment); an unloaded one returns with its clips. The host
// writes its resolved count into the payload, so the replica ends on the host's result; the presser already holds it (a no-op).
void craftEquipVehicles(Json::Value& payload, Base* base, Craft* craft, const RuleItem* item)
{
	ItemContainer* store = base->getStorageItems();
	const RuleItem* ammo = item->getVehicleClipAmmo();
	const int perVehicle = ammo ? item->getVehicleClipsLoaded() : 0;
	const bool clips = ammo && perVehicle > 0;
	const int size = item->getVehicleUnit()->getArmor()->getTotalSize();
	const int current = craft->getVehicleCount(item->getType());
	int target = std::max(0, payload.get("count", 0).asInt());
	if (target > current)
	{
		int add = std::min(target - current, store->getItem(item)); // the vehicles the base holds,
		add = std::min(add, craft->validateAddingVehicles(size));   // the craft's room,
		if (clips) add = std::min(add, store->getItem(ammo) / perVehicle); // the clips to arm them
		for (int i = 0; i < add; ++i)
		{
			if (clips) store->removeItem(ammo, perVehicle);
			store->removeItem(item);
			craft->getVehicles()->push_back(new Vehicle(item, item->getVehicleClipSize(), size));
			craft->resetCustomDeployment(); // adding a vehicle into a craft invalidates a custom craft deployment (vanilla)
		}
		target = current + std::max(0, add);
	}
	else if (target < current)
	{
		store->addItem(item, current - target);
		if (clips) store->addItem(ammo, perVehicle * (current - target));
		Collections::deleteIf(*craft->getVehicles(), current - target, [&](Vehicle* v) { return v->getRules() == item; });
	}
	if (connectionTCP::getHost()) payload["count"] = target; // the host's resolution rides the broadcast
	Log(LOG_INFO) << "[SHARED] craft_equip vehicles: " << item->getType() << " " << current << " -> " << target << ", craft " << craft->getId();
}

// Moves (non-vehicle) @a item between @a base's stores and @a craft until the
// craft holds @a target, within what the stores hold and the craft's capacity.
static void setCraftItemCount(Craft* craft, Base* base, const RuleItem* item, int target)
{
	ItemContainer* craftItems = craft->getItems();
	ItemContainer* store = base->getStorageItems();
	int current = craftItems->getItem(item);
	if (target < 0) target = 0;

	// Clamp UP by base availability (never move more than the base holds) and by
	// the craft's capacity, mirroring CraftEquipmentState::moveRightByValue's
	// vanilla gates. Host and replica run this on the one replicated world, so
	// the clamp is identical on both -> they converge with no drift.
	if (target > current + store->getItem(item))
		target = current + store->getItem(item);
	if (target > current)
	{
		int addByCount = craft->getMaxItemsClamped() - craftItems->getTotalQuantity();
		if (addByCount < 0) addByCount = 0;
		if (target - current > addByCount) target = current + addByCount;
		if (item->getSize() > 0.0)
		{
			double freeSpace = craft->getMaxStorageSpaceClamped() + 0.05 - craft->getTotalItemStorageSize();
			int addBySize = (int)std::floor(freeSpace / item->getSize());
			if (addBySize < 0) addBySize = 0;
			if (target - current > addBySize) target = current + addBySize;
		}
	}

	int delta = target - current;
	if (delta > 0)      { craftItems->addItem(item, delta);   store->removeItem(item, delta); }
	else if (delta < 0) { craftItems->removeItem(item, -delta); store->addItem(item, -delta); }
}

void craftEquipApply(Game* game, Json::Value& payload, Base* base, int seat)
{
	if (!base) return;
	Craft* craft = resolveOrderCraft(game, payload, base);
	const RuleItem* item = game->getMod()->getItem(payload.get("item", "").asString(), false);
	if (!craft || !item) return;
	if (item->getVehicleUnit())
	{
		if (game->getSavedGame()->isSeparateCoopCampaign())
			SeparateEcon::applyVehicleEquip(game, payload, base, seat);
		else
			craftEquipVehicles(payload, base, craft, item); // HWPs: whole vehicles with their clip ammo
		return;
	}
	setCraftItemCount(craft, base, item, payload.get("count", 0).asInt());
}

// SHARED vehicles on the craft equipment screen: CraftEquipmentState's own
// vehicle moves (a vehicle and its ammo leave the stores together and come back
// together; a vehicle needs craft room and a full clip load), on the shared world.
static void setSharedVehicleCount(Craft* craft, Base* base, const RuleItem* item, int target)
{
	ItemContainer* store = base->getStorageItems();
	const int current = craft->getVehicleCount(item->getType());
	const RuleItem* ammo = item->getVehicleClipAmmo();
	const int ammoPerVehicle = item->getVehicleClipsLoaded();
	if (target < current)
	{
		const int change = current - target;
		store->addItem(item, change);
		if (ammo) store->addItem(ammo, ammoPerVehicle * change);
		Collections::deleteIf(*craft->getVehicles(), change,
			[&](Vehicle* v) { return v->getRules() == item; });
	}
	else if (target > current)
	{
		const int size = item->getVehicleUnit()->getArmor()->getTotalSize();
		int change = std::min(target - current, store->getItem(item));
		change = std::min(change, craft->validateAddingVehicles(size));
		if (ammo && ammoPerVehicle > 0)
			change = std::min(change, store->getItem(ammo) / ammoPerVehicle);
		for (int i = 0; i < change; ++i)
		{
			if (ammo) store->removeItem(ammo, ammoPerVehicle);
			store->removeItem(item);
			craft->getVehicles()->push_back(new Vehicle(item, item->getVehicleClipSize(), size));
			craft->resetCustomDeployment();
		}
	}
}

// craft_loadout payload: { craftId, craftType, onlyAdd, listed:[itemType...],
// template:{itemType: qty} }, baseId = the craft's home-base index. A craft
// equipment template load (CraftEquipmentState::loadGlobalLoadout): listed are
// the item types the screen shows, template the slot's contents. Unless onlyAdd,
// every listed item first goes back to the stores; then each listed item takes
// its template quantity on top, within the stores and the craft's capacity
// (the screen's moves with the alternate management off, as vanilla's load
// does). The host turns that into steps (absolute counts, in order) and the
// "cannot re-equip" shortfall; every machine runs the same steps, and the
// player who loaded sees the shortfall. Separate: a player's own vehicles
// only, with the craft screen's owner priority, and only the base owner may
// load a template.
bool craftLoadoutValidate(Game* game, const Json::Value& payload, Base* base, int seat,
                          int64_t& cost, std::string& failReason)
{
	cost = 0;
	if (!base) { failReason = "base not found"; return false; }
	if (!resolveOrderCraft(game, payload, base)) { failReason = "craft not found"; return false; }
	if (!payload["listed"].isArray() || !payload["template"].isObject())
		{ failReason = "bad craft loadout"; return false; }
	if (game->getSavedGame()->isSeparateCoopCampaign()
		&& !base->isOwnedByPlayer(connectionTCP::seatName(seat)))
		{ failReason = "Only the base owner can change craft equipment"; return false; }
	return true;
}

void craftLoadoutApply(Game* game, Json::Value& payload, Base* base, int seat)
{
	if (!base || !game->getSavedGame()) return;
	Craft* craft = resolveOrderCraft(game, payload, base);
	if (!craft) return;
	const bool separate = game->getSavedGame()->isSeparateCoopCampaign();
	auto countOf = [&](const RuleItem* item)
	{
		if (!item->getVehicleUnit()) return craft->getItems()->getItem(item);
		return separate
			? SeparateEcon::vehicleSelectionCount(game, craft, item->getType(), seat)
			: craft->getVehicleCount(item->getType());
	};
	const bool onlyAdd = payload.get("onlyAdd", false).asBool();
	const Json::Value& tmpl = payload["template"];
	std::map<std::string, int> before;
	if (isHost())
	{
		for (const auto& name : tmpl.getMemberNames())
			if (const RuleItem* item = game->getMod()->getItem(name, false))
				before[name] = countOf(item);
		Json::Value steps(Json::arrayValue);
		std::vector<std::pair<std::string, int>> adds;
		for (const auto& entry : payload["listed"])
		{
			const std::string type = entry.asString();
			const RuleItem* item = game->getMod()->getItem(type, false);
			if (!item) continue;
			const int now = countOf(item);
			if (!onlyAdd && now > 0)
			{
				Json::Value step;
				step["item"] = type;
				step["count"] = 0;
				steps.append(step);
			}
			const int qty = tmpl.get(type, 0).asInt();
			if (qty > 0) adds.push_back({ type, (onlyAdd ? now : 0) + qty });
		}
		for (const auto& add : adds)
		{
			Json::Value step;
			step["item"] = add.first;
			step["count"] = add.second;
			steps.append(step);
		}
		payload["steps"] = steps;
	}
	for (auto& step : payload["steps"])
	{
		const RuleItem* item = game->getMod()->getItem(step.get("item", "").asString(), false);
		if (!item) continue;
		if (!item->getVehicleUnit())
			setCraftItemCount(craft, base, item, step.get("count", 0).asInt());
		else if (separate)
		{
			// applyVehicleEquip names the craft itself; on the host it writes the
			// resolved count and owners into the step for the replicas.
			step["craftId"] = craft->getId();
			step["craftType"] = craft->getRules()->getType();
			SeparateEcon::applyVehicleEquip(game, step, base, seat);
		}
		else
			setSharedVehicleCount(craft, base, item, step.get("count", 0).asInt());
	}
	if (isHost())
	{
		Json::Value missing(Json::arrayValue);
		for (const auto& name : tmpl.getMemberNames())
		{
			const RuleItem* item = game->getMod()->getItem(name, false);
			if (!item) continue;
			const int got = countOf(item) - (onlyAdd ? before[name] : 0);
			const int short_ = tmpl[name].asInt() - got;
			if (short_ > 0)
			{
				Json::Value m;
				m["item"] = name;
				m["qty"] = short_;
				missing.append(m);
			}
		}
		payload["missing"] = missing;
	}
	// The player who loaded the template sees what was missing (vanilla's report).
	if (seat == connectionTCP::localSeat() && payload["missing"].isArray()
		&& !payload["missing"].empty())
	{
		const std::string craftName = craft->getName(game->getLanguage());
		std::vector<ReequipStat> stats;
		for (const auto& m : payload["missing"])
		{
			const RuleItem* item = game->getMod()->getItem(m.get("item", "").asString(), false);
			if (!item) continue;
			ReequipStat stat = { item->getType(), m.get("qty", 0).asInt(), craftName, item->getListOrder() };
			stats.push_back(stat);
		}
		std::sort(stats.begin(), stats.end(), [](const ReequipStat& a, const ReequipStat& b)
			{
				return a.listOrder < b.listOrder;
			});
		if (!stats.empty())
			game->pushState(new CannotReequipState(stats, base));
	}
}

// ---- PRD-J09 GAP-5b: shared-world base-screen store mutators ------------------
// Same class as GAP-5 (CraftEquipmentState): a base-screen action moves items in
// and out of the host-authoritative base stores (the exact quantity the GAP-4
// chkItems sums). On a replica those mutations ran ungated and drifted chkItems
// from the host; each now routes an ABSOLUTE end-state command instead. The host
// validates + applies + broadcasts; the applier is pure world-state math run on
// the one replicated world, so host and replica converge with no drift.

// craft_rearm payload: { craftId, craftType, slot, weapon }. weapon="" dismounts
// the slot. baseId = the craft's home-base index. End-state = which craft-weapon
// type is mounted in `slot` (last-write-wins). Mirrors CraftWeaponsState::
// lstWeaponsClick's launcher/clip store moves; clip rearm-over-time stays host-sim
// (J04), as does the deferred re-equip-with-loaded-clips case (checksum backstop).
bool craftRearmValidate(Game* game, const Json::Value& payload, Base* base, int /*seat*/,
                        int64_t& cost, std::string& failReason)
{
	cost = 0; // no funds effect; broadcast still carries authoritative getFunds()
	if (!base) { failReason = "base not found"; return false; }
	Craft* craft = resolveOrderCraft(game, payload, base);
	if (!craft) { failReason = "craft not found"; return false; }
	int slot = payload.get("slot", -1).asInt();
	if (slot < 0 || slot >= (int)craft->getWeapons()->size()) { failReason = "bad weapon slot"; return false; }
	std::string wtype = payload.get("weapon", "").asString();
	const RuleCraftWeapon* selRule = nullptr;
	if (!wtype.empty())
	{
		selRule = game->getMod()->getCraftWeapon(wtype, false);
		if (!selRule) { failReason = "unknown craft weapon"; return false; }
		if (!craft->getRules()->isValidWeaponSlot((size_t)slot, selRule->getWeaponType()))
		{ failReason = "weapon not valid for slot"; return false; }
	}

	// issue #121: re-run the SAME four capacity gates the client's CraftWeaponsState
	// enforces, against the host-authoritative craft. The client gate can pass on a
	// stale replica view; the host is the single authority, so it must reject an
	// over-capacity swap here rather than apply it and desync/deploy-fault later.
	CraftWeapon* current = craft->getWeapons()->at(slot);
	const RuleCraftWeapon* curRule = current ? current->getRules() : nullptr;
	std::string capErr = CraftWeaponsState::equipCapacityError(game->getMod(), craft, selRule, curRule);
	if (!capErr.empty()) { failReason = capErr; return false; }
	return true;
}

void craftRearmApply(Game* game, Json::Value& payload, Base* base, int /*seat*/)
{
	if (!base) return;
	Craft* craft = resolveOrderCraft(game, payload, base);
	if (!craft) return;
	int slot = payload.get("slot", -1).asInt();
	if (slot < 0 || slot >= (int)craft->getWeapons()->size()) return;
	std::string wtype = payload.get("weapon", "").asString();
	const RuleCraftWeapon* selRule = wtype.empty() ? nullptr
		: game->getMod()->getCraftWeapon(wtype, false);
	if (!wtype.empty() && !selRule) return;

	ItemContainer* store = base->getStorageItems();
	CraftWeapon* current = craft->getWeapons()->at(slot);
	const RuleCraftWeapon* curRule = current ? current->getRules() : nullptr;
	if (curRule == selRule) return; // idempotent: a late/duplicate apply can't double-charge

	// Dismount the current weapon: return the launcher + any loaded clips to the
	// shared stores (mirrors lstWeaponsClick "Remove current weapon").
	if (current)
	{
		store->addItem(current->getRules()->getLauncherItem());
		store->addItem(current->getRules()->getClipItem(), current->getClipsLoaded());
		craft->addCraftStats(-current->getRules()->getBonusStats());
		craft->setShield(craft->getShield()); // exploit protection (as vanilla)
		delete current;
		craft->getWeapons()->at(slot) = 0;
	}

	// Mount the new weapon: consume one launcher from the shared stores. Only if
	// available, so a race can never drive stores negative; deterministic on host
	// + replica -> they converge. Clips load over time via the host sim (vanilla).
	if (selRule && store->getItem(selRule->getLauncherItem()) > 0)
	{
		CraftWeapon* cw = new CraftWeapon(const_cast<RuleCraftWeapon*>(selRule), 0);
		craft->addCraftStats(selRule->getBonusStats());
		store->removeItem(selRule->getLauncherItem());
		craft->getWeapons()->at(slot) = cw;
	}
	craft->checkup();
}

// soldier_rank payload: { soldierId, rank }. a manual promotion
// or demotion (SoldierRankState) keeps vanilla's local write and submits the result as an
// absolute end-state. HOST: when the rank differs, re-run the vanilla openings rule against
// the host's world and apply or keep it; ALWAYS write the resolved rank into the payload
// (the buy idiom: the broadcast carries it). REPLICA (the initiator included): adopt the
// payload's rank. A lost race for the last opening is undone by the host's result.
bool soldierRankValidate(Game* /*game*/, const Json::Value& payload, Base* base, int /*seat*/,
                         int64_t& cost, std::string& failReason)
{
	cost = 0;
	if (!base) { failReason = "base not found"; return false; }
	if (!findSoldier(base, payload.get("soldierId", -1).asInt())) { failReason = "soldier not found"; return false; }
	int rank = payload.get("rank", -1).asInt();
	if (rank < (int)RANK_ROOKIE || rank > (int)RANK_COMMANDER) { failReason = "bad rank"; return false; }
	return true;
}
void soldierRankApply(Game* game, Json::Value& payload, Base* base, int /*seat*/)
{
	if (!base) return;
	Soldier* s = findSoldier(base, payload.get("soldierId", -1).asInt());
	int rank = payload.get("rank", -1).asInt();
	if (!s || rank < (int)RANK_ROOKIE || rank > (int)RANK_COMMANDER) return;
	if (connectionTCP::getHost())
	{
		SavedGame* save = game ? game->getSavedGame() : nullptr;
		if (save && s->getRank() != (SoldierRank)rank
			&& PromotionOpenings(save->getAllActiveSoldiers(), game->getMod()).isManualPromotionPossible(s, (SoldierRank)rank))
			s->setRank((SoldierRank)rank);
		payload["rank"] = (int)s->getRank(); // the resolved rank rides the broadcast
	}
	else
	{
		s->setRank((SoldierRank)rank);
	}
}

// soldier_nationality payload: { soldierId, nationality }. the flag on the
// soldier screen (SoldierInfoState::btnFlagClick) keeps vanilla's local write and submits the
// result as an absolute end-state; both roles set it (last-write-wins, like soldier_rename).
bool soldierNationalityValidate(Game* /*game*/, const Json::Value& payload, Base* base, int /*seat*/,
                                int64_t& cost, std::string& failReason)
{
	cost = 0;
	if (!base) { failReason = "base not found"; return false; }
	if (!findSoldier(base, payload.get("soldierId", -1).asInt())) { failReason = "soldier not found"; return false; }
	if (payload.get("nationality", -1).asInt() < 0) { failReason = "bad nationality"; return false; }
	return true;
}
void soldierNationalityApply(Game* /*game*/, Json::Value& payload, Base* base, int /*seat*/)
{
	if (!base) return;
	Soldier* s = findSoldier(base, payload.get("soldierId", -1).asInt());
	int nationality = payload.get("nationality", -1).asInt();
	if (s && nationality >= 0) s->setNationality(nationality);
}

// soldier_psi_training payload: { soldierId, psi }.
// a psi allocation (AllocatePsiTrainingState)
// keeps vanilla's local write and submits the soldier's flags as an absolute end-state. The host refuses a
// soldier the sending seat does not own. HOST: re-run vanilla's gates against the host's world,
// apply or keep, and ALWAYS write the resolved flags into the payload (the broadcast carries them).
// REPLICA (the initiator included): adopt the payload's flags. A lost race for the last place is undone.
bool soldierPsiTrainingValidate(Game* /*game*/, const Json::Value& payload, Base* base, int seat,
                                int64_t& cost, std::string& failReason)
{
	cost = 0;
	if (!base) { failReason = "base not found"; return false; }
	Soldier* s = findSoldier(base, payload.get("soldierId", -1).asInt());
	if (!s) { failReason = "soldier not found"; return false; }
	if (s->getOwnerPlayerId() != seat) { failReason = "not your soldier"; return false; } // own soldiers only
	return true;
}
void soldierPsiTrainingApply(Game* game, Json::Value& payload, Base* base, int /*seat*/)
{
	if (!base) return;
	Soldier* s = findSoldier(base, payload.get("soldierId", -1).asInt());
	if (!s) return;
	bool psi = payload.get("psi", false).asBool();
	if (connectionTCP::getHost())
	{
		// vanilla's gates (AllocatePsiTrainingState :492-502) against the HOST's world
		if (psi && !s->isInPsiTraining()
			&& (s->getRules()->getTrainingStatCaps().psiSkill <= 0 || s->isFullyPsiTrained()
				|| base->getUsedPsiLabs() >= base->getAvailablePsiLabs()))
			psi = false;
		s->setPsiTraining(psi);
		payload["psi"] = s->isInPsiTraining(); // the resolved flag rides the broadcast
	}
	else
	{
		s->setPsiTraining(psi);
	}
	// both roles: the stat string with THIS machine's psiStrengthEval (AllocatePsiTrainingState::btnOkClick)
	if (game && game->getSavedGame())
		s->calcStatString(game->getMod()->getStatStrings(), Options::psiStrengthEval &&
			game->getSavedGame()->isResearched(game->getMod()->getPsiRequirements()));
}

// soldier_armor payload: { soldierId, armor }. baseId = the soldier's base index.
// End-state = which armor the soldier wears (identity swap, last-write-wins - the
// J09 "model the payload to the state, not literally a count" adaptation). Mirrors
// SoldierArmorState / CraftArmorState: return the old armor's store item + consume
// the new one against the shared stores.
// Separate Campaign: a player changes only their own soldier's armor,
// also at another player's base, where the armor comes from that base's stores.
bool soldierArmorValidate(Game* game, const Json::Value& payload, Base* base, int seat,
                          int64_t& cost, std::string& failReason)
{
	cost = 0;
	if (!base) { failReason = "base not found"; return false; }
	Soldier* s = findSoldier(base, payload.get("soldierId", -1).asInt());
	if (!s) { failReason = "soldier not found"; return false; }
	if (!separateSoldierOwnerOk(game, s, seat))
		{ failReason = "STR_COOP_NOT_YOUR_SOLDIER"; return false; }
	Armor* next = game->getMod()->getArmor(payload.get("armor", "").asString(), false);
	if (!next) { failReason = "unknown armor"; return false; }
	// The armor screen offers a stored armor only while the base holds one (or
	// the soldier's current armor uses the same store item); a stale replica can
	// still ask for the last one twice.
	SavedGame* save = game->getSavedGame();
	if (save && save->getMonthsPassed() != -1 && next != s->getArmor()
		&& next->getStoreItem() && next->getStoreItem() != s->getArmor()->getStoreItem()
		&& base->getStorageItems()->getItem(next->getStoreItem()) < 1)
		{ failReason = "armor not in base stores"; return false; }

	// issue #121: re-run the client's craft-space gate (SoldierArmorState::lstArmorClick)
	// against the host-authoritative world. If the soldier rides a craft, a larger armor
	// must still fit; the client gate can pass on a stale replica view, so the host is the
	// backstop that keeps a shared craft from being pushed over capacity.
	Craft* craft = s->getCraft();
	if (craft && !craft->validateArmorChange(s->getArmor()->getSize(), next->getSize()))
	{ failReason = "STR_NOT_ENOUGH_CRAFT_SPACE"; return false; }
	if (s->getOwnerPlayerId() != seat) { failReason = "not your soldier"; return false; } // own soldiers only
	return true;
}

void soldierArmorApply(Game* game, Json::Value& payload, Base* base, int /*seat*/)
{
	if (!base) return;
	Soldier* s = findSoldier(base, payload.get("soldierId", -1).asInt());
	Armor* next = game->getMod()->getArmor(payload.get("armor", "").asString(), false);
	if (!s || !next) return;
	Armor* prev = s->getArmor();
	if (prev == next) return; // idempotent
	// Store bookkeeping only in a live campaign (monthsPassed != -1), matching the
	// UI screens; pre-game (new battle) never touches stores.
	SavedGame* save = game->getSavedGame();
	if (save && save->getMonthsPassed() != -1)
	{
		if (prev->getStoreItem()) base->getStorageItems()->addItem(prev->getStoreItem());
		if (next->getStoreItem()) base->getStorageItems()->removeItem(next->getStoreItem());
	}
	s->setArmor(next, true);
	if (payload.get("tmpl", false).asBool()) return; // a template's armor change leaves the last-selected armor (vanilla)
	if (save) save->setLastSelectedArmor(next->getType());
}

// ---- soldier_equip - a SHARED base equipment screen's OK --------------------------------------------------------
// payload: { soldiers: [{id, layout, personal, personalArmor}] }, baseId = the screen's base. layout / personal = the soldier's equipment
// layout and personal layout as vanilla's own save writes them (Soldier.cpp :381-:386; EquipmentLayoutItem::save) under key "l";
// personalArmor = the personal layout's armor type ("" = none). Player-origin from either seat at its base-screen OK: one entry per OWN
// soldier whose record changed. The host writes an entry only for a soldier the sending seat owns and broadcasts its
// own record for any other entry; a replica adopts every entry. No stores move here (option ON's craft moves are committed separately).
Json::Value g_baseEquipMark(Json::nullValue); // the open base screen's records {base: index, soldiers: {"<id>": record}}

std::string equipYaml(const std::vector<EquipmentLayoutItem*>& layout)
{
	if (layout.empty()) return std::string(); // "" = an empty layout (never parsed)
	YAML::YamlRootNodeWriter w;
	w.setAsMap();
	w.write("l", layout, [](YAML::YamlNodeWriter& n, EquipmentLayoutItem* i) { i->save(n.write()); });
	return w.emit().yaml;
}

// Vanilla's own load (Soldier.cpp :243-:251) of an equipYaml string into @a out (emptied first); an item this mod cannot load is skipped.
void equipFromYaml(Game* game, const std::string& yaml, std::vector<EquipmentLayoutItem*>& out)
{
	for (auto* li : out) delete li;
	out.clear();
	if (yaml.empty()) return;
	try
	{
		YAML::YamlRootNodeReader reader(YAML::YamlString{yaml}, "soldierEquip");
		for (const auto& n : reader["l"].children())
		{
			try { out.push_back(new EquipmentLayoutItem(n, game->getMod())); }
			catch (const std::exception& e) { Log(LOG_ERROR) << "[SHARED] soldier_equip: layout item not loaded: " << e.what(); }
		}
	}
	catch (const std::exception& e) { Log(LOG_ERROR) << "[SHARED] soldier_equip: layout not read: " << e.what(); }
}

Json::Value soldierEquipRecord(Soldier* s)
{
	Json::Value r(Json::objectValue);
	r["id"] = s->getId();
	r["layout"] = equipYaml(*s->getEquipmentLayout());
	r["personal"] = equipYaml(*s->getPersonalEquipmentLayout());
	r["personalArmor"] = s->getPersonalEquipmentArmor() ? s->getPersonalEquipmentArmor()->getType() : std::string();
	r["name"] = s->getName(); // a rename typed on the base screen rides the record
	return r;
}

// Writes the present fields of record @a r into @a s.
void soldierEquipAdopt(Game* game, Soldier* s, const Json::Value& r)
{
	if (r.isMember("layout")) equipFromYaml(game, r["layout"].asString(), *s->getEquipmentLayout());
	if (r.isMember("personal")) equipFromYaml(game, r["personal"].asString(), *s->getPersonalEquipmentLayout());
	if (r.isMember("personalArmor")) s->setPersonalEquipmentArmor(game->getMod()->getArmor(r["personalArmor"].asString(), false));
	if (r.isMember("name")) s->setName(r["name"].asString());
}

bool soldierEquipValidate(Game* /*game*/, const Json::Value& payload, Base* base, int /*seat*/,
                          int64_t& cost, std::string& failReason)
{
	cost = 0;
	if (!base) { failReason = "base not found"; return false; }
	if (!payload["soldiers"].isArray()) { failReason = "soldier not found"; return false; }
	return true;
}

void soldierEquipApply(Game* game, Json::Value& payload, Base* base, int seat)
{
	if (!game || !base) return;
	const bool host = connectionTCP::getHost();
	const int bi = baseIndex(game, base);
	const bool marked = g_baseEquipMark.isObject() && g_baseEquipMark.get("base", -1).asInt() == bi;
	Json::Value resolved(Json::arrayValue);
	int adopted = 0, kept = 0;
	for (const auto& r : payload["soldiers"])
	{
		Soldier* s = findSoldier(base, r.get("id", -1).asInt());
		if (!s) continue; // not at this base (any more): left out of the broadcast
		if (host && s->getOwnerPlayerId() != seat)
		{
			resolved.append(soldierEquipRecord(s)); // not the sender's soldier - the host's record rides instead
			++kept;
			continue;
		}
		soldierEquipAdopt(game, s, r);
		resolved.append(r);
		++adopted;
		if (marked) g_baseEquipMark["soldiers"][std::to_string(s->getId())] = soldierEquipRecord(s); // an open screen keeps it
	}
	if (host) payload["soldiers"] = resolved;
	Log(LOG_INFO) << "[SHARED] soldier_equip: " << adopted << " adopted, " << kept << " kept by the host, base " << bi;
}

// a rename applied while a base screen is open (the partner's soldier_rename) refreshes that soldier's name in the open
// screen's mark, so the screen's OK does not put the old name back (the open screen's refresh rule, the name field only).
void baseEquipMarkName(Soldier* s)
{
	if (!s || !g_baseEquipMark.isObject()) return;
	const std::string key = std::to_string(s->getId());
	if (g_baseEquipMark["soldiers"].isMember(key)) g_baseEquipMark["soldiers"][key]["name"] = s->getName();
}

// ---- craft_deployment - a SHARED craft type's generic deployment (the Ufopaedia craft preview's save) ----------
// payload: { craftType, saved, positions [[x, y, z, dir], ...] (saved only) }, baseId -1 (no base; base_new's precedent). Player-origin from
// either seat right after vanilla's own local save or delete (SavedBattleGame::saveDummyCraftDeployment); both roles repeat vanilla's write:
// every craft of that type loses its own custom deployment, then the type's entry is written or erased. Last write wins.
bool craftDeploymentValidate(Game* game, const Json::Value& payload, Base* /*base*/, int /*seat*/,
                             int64_t& cost, std::string& /*failReason*/)
{
	cost = 0;
	return game->getMod()->getCraft(payload.get("craftType", "").asString(), false) != nullptr; // a refusal reads "rejected"
}

void craftDeploymentApply(Game* game, Json::Value& payload, Base* /*base*/, int /*seat*/)
{
	SavedGame* sg = game ? game->getSavedGame() : nullptr;
	const RuleCraft* rule = sg ? game->getMod()->getCraft(payload.get("craftType", "").asString(), false) : nullptr;
	if (!rule) return;
	for (auto* xbase : *sg->getBases())
		for (auto* xcraft : *xbase->getCrafts())
			if (xcraft->getRules() == rule) xcraft->resetCustomDeployment(); // vanilla: a type deployment invalidates every craft's own one
	auto& data = sg->getCustomRuleCraftDeployments();
	const bool saved = payload.get("saved", false).asBool();
	const Json::Value positions = payload.get("positions", Json::Value(Json::arrayValue));
	if (!saved)
	{
		data.erase(rule->getType());
	}
	else
	{
		RuleCraftDeployment deploy;
		for (const auto& p : positions)
			if (p.isArray() && p.size() == 4) deploy.push_back({ p[0].asInt(), p[1].asInt(), p[2].asInt(), p[3].asInt() });
		data[rule->getType()] = deploy;
	}
	Log(LOG_INFO) << "[SHARED] craft_deployment: " << rule->getType() << (saved ? " saved, " : " deleted, ") << positions.size() << " position(s)";
}

// soldier_training payload: { kind: "martial" | "psi", soldiers: [{ id, training,
// queued }] }. baseId = the soldiers' base. The training screens send the flags a
// click or assign-all / de-assign-all sets; the host runs the training, so the
// flags live in its world. SHARED: any soldier, as the screen allows today.
// Separate: only the requester's own soldiers, also at another player's base.
// The checks are the screen's: no training for a fully trained soldier, a
// wounded one is only queued (martial), and the base must have the room.
bool soldierTrainingValidate(Game* game, const Json::Value& payload, Base* base, int seat,
                             int64_t& cost, std::string& failReason)
{
	cost = 0;
	if (!base) { failReason = "base not found"; return false; }
	const std::string kind = payload.get("kind", "").asString();
	if (kind != "martial" && kind != "psi") { failReason = "unknown training"; return false; }
	const bool psi = kind == "psi";
	const Json::Value& soldiers = payload["soldiers"];
	if (!soldiers.isArray() || soldiers.empty()) { failReason = "no soldiers"; return false; }
	int added = 0;
	int removed = 0;
	for (const auto& entry : soldiers)
	{
		Soldier* s = findSoldier(base, entry.get("id", -1).asInt());
		if (!s) { failReason = "soldier not found"; return false; }
		if (!separateSoldierOwnerOk(game, s, seat))
			{ failReason = "STR_COOP_NOT_YOUR_SOLDIER"; return false; }
		const bool training = entry.get("training", false).asBool();
		const bool now = psi ? s->isInPsiTraining() : s->isInTraining();
		if (training && !now)
		{
			const bool trainable = psi
				? s->getRules()->getTrainingStatCaps().psiSkill > 0 && !s->isFullyPsiTrained()
				: !s->isFullyTrained() && !s->isWounded();
			if (!trainable) { failReason = "soldier cannot train"; return false; }
			++added;
		}
		else if (!training && now) ++removed;
		if (!psi && entry.get("queued", false).asBool() && s->isFullyTrained())
			{ failReason = "soldier cannot train"; return false; }
	}
	const int used = psi ? base->getUsedPsiLabs() : base->getUsedTraining();
	const int room = psi ? base->getAvailablePsiLabs() : base->getAvailableTraining();
	if (added > 0 && used - removed + added > room)
		{ failReason = "no free training space"; return false; }
	return true;
}

void soldierTrainingApply(Game* game, Json::Value& payload, Base* base, int /*seat*/)
{
	if (!base) return;
	const bool psi = payload.get("kind", "").asString() == "psi";
	for (const auto& entry : payload["soldiers"])
	{
		Soldier* s = findSoldier(base, entry.get("id", -1).asInt());
		if (!s) continue;
		if (psi)
		{
			s->setPsiTraining(entry.get("training", false).asBool());
			// both roles: the stat string with THIS machine's psiStrengthEval (AllocatePsiTrainingState::btnOkClick)
			if (game && game->getSavedGame())
				s->calcStatString(game->getMod()->getStatStrings(), Options::psiStrengthEval &&
					game->getSavedGame()->isResearched(game->getMod()->getPsiRequirements()));
		}
		else
		{
			s->setTraining(entry.get("training", false).asBool());
			s->setReturnToTrainingWhenHealed(entry.get("queued", false).asBool());
		}
	}
}

// ---- equip_template - a SHARED template save ------------------------------------
// payload: { kind: "layout" | "loadout", index, name, layout + armor (kind layout: the slot's equipYaml and armor type) | items {type: count}
// (kind loadout) }, baseId = the saving screen's base. Player-origin from either seat right after vanilla's own local save; the whole slot
// travels and both roles write it, so the one shared world keeps ONE template set (last write wins). No store, soldier or craft is touched.
bool equipTemplateValidate(Game* /*game*/, const Json::Value& payload, Base* base, int /*seat*/,
                           int64_t& cost, std::string& failReason)
{
	cost = 0;
	if (!base) { failReason = "base not found"; return false; }
	const std::string kind = payload.get("kind", "").asString();
	const int index = payload.get("index", -1).asInt();
	if (kind == "layout") return index >= 0 && index < SavedGame::MAX_EQUIPMENT_LAYOUT_TEMPLATES; // a refusal reads "rejected"
	if (kind == "loadout") return index >= 0 && index < SavedGame::MAX_CRAFT_LOADOUT_TEMPLATES;
	return false;
}

void equipTemplateApply(Game* game, Json::Value& payload, Base* /*base*/, int /*seat*/)
{
	SavedGame* sg = game ? game->getSavedGame() : nullptr;
	if (!sg) return;
	const int index = payload.get("index", -1).asInt();
	const std::string kind = payload.get("kind", "").asString();
	if (kind == "layout" && index >= 0 && index < SavedGame::MAX_EQUIPMENT_LAYOUT_TEMPLATES)
	{
		equipFromYaml(game, payload.get("layout", "").asString(), *sg->getGlobalEquipmentLayout(index));
		sg->setGlobalEquipmentLayoutArmor(index, payload.get("armor", "").asString());
		sg->setGlobalEquipmentLayoutName(index, payload.get("name", "").asString());
	}
	else if (kind == "loadout" && index >= 0 && index < SavedGame::MAX_CRAFT_LOADOUT_TEMPLATES)
	{
		ItemContainer* tmpl = sg->getGlobalCraftLoadout(index);
		tmpl->clear();
		const Json::Value& items = payload["items"];
		for (const auto& type : items.getMemberNames())
			if (const RuleItem* rule = game->getMod()->getItem(type, false)) tmpl->addItem(rule, items[type].asInt());
		sg->setGlobalCraftLoadoutName(index, payload.get("name", "").asString());
	}
	Log(LOG_INFO) << "[SHARED] equip_template: " << kind << " " << index << " written";
}

// THIS machine's open option-ON staging window, null = closed: {base: index, crafts: [{craftId, craftType, items
// {type: count}}], seats {"<soldier id>": {craftId, craftType} or null}}. craftStageOpen opens it, craftStageClose commits and closes it,
// notifyWorldAdopted / resetSessionQueues drop it; while it is open verifyWorldChecksum skips this machine's check.
Json::Value g_craftStage(Json::nullValue);

// fac_disable { x, y, disabled }, baseId = the base index: the host re-checks vanilla's gate, applies and broadcasts the resolved flag; a replica adopts it.
bool facDisableValidate(Game* /*game*/, const Json::Value& payload, Base* base, int /*seat*/,
                        int64_t& cost, std::string& failReason)
{
	cost = 0;
	if (!base) { failReason = "base not found"; return false; }
	int x = payload.get("x", -1).asInt();
	int y = payload.get("y", -1).asInt();
	for (auto* f : *base->getFacilities())
		if (f->getX() == x && f->getY() == y && f->getRules()->isMindShield()) return true;
	failReason = "mind shield not found";
	return false;
}
void facDisableApply(Game* /*game*/, Json::Value& payload, Base* base, int /*seat*/)
{
	if (!base) return;
	int x = payload.get("x", -1).asInt();
	int y = payload.get("y", -1).asInt();
	BaseFacility* fac = nullptr;
	for (auto* f : *base->getFacilities())
		if (f->getX() == x && f->getY() == y) { fac = f; break; }
	if (!fac || !fac->getRules()->isMindShield()) return;
	if (connectionTCP::getHost())
	{
		if (fac->getBuildTime() == 0) // vanilla's gate (BasescapeState::viewRightClick)
			fac->setDisabled(payload.get("disabled", false).asBool());
		payload["disabled"] = fac->getDisabled(); // the resolved flag rides the broadcast
	}
	else
	{
		fac->setDisabled(payload.get("disabled", false).asBool());
	}
}

// craft_weapon_disable { craftId, craftType, slot, disabled }: as fac_disable; the host also decides the craft re-check, never for a craft that is out.
bool craftWeaponDisableValidate(Game* game, const Json::Value& payload, Base* base, int /*seat*/,
                                int64_t& cost, std::string& failReason)
{
	cost = 0;
	if (!base) { failReason = "base not found"; return false; }
	Craft* craft = resolveOrderCraft(game, payload, base);
	if (!craft) { failReason = "craft not found"; return false; }
	int slot = payload.get("slot", -1).asInt();
	if (slot < 0 || slot >= (int)craft->getWeapons()->size() || !craft->getWeapons()->at(slot))
	{ failReason = "no weapon in slot"; return false; }
	return true;
}
void craftWeaponDisableApply(Game* game, Json::Value& payload, Base* base, int /*seat*/)
{
	if (!base) return;
	Craft* craft = resolveOrderCraft(game, payload, base);
	if (!craft) return;
	int slot = payload.get("slot", -1).asInt();
	if (slot < 0 || slot >= (int)craft->getWeapons()->size()) return;
	CraftWeapon* w = craft->getWeapons()->at(slot);
	if (!w) return;
	bool disabled = payload.get("disabled", false).asBool();
	bool checkup;
	if (connectionTCP::getHost())
	{
		// vanilla re-checks on enabling (CraftInfoState::btnWIconClick), a screen an out craft never reaches
		checkup = !disabled && craft->getStatus() != "STR_OUT";
		payload["checkup"] = checkup; // the host's decision rides the broadcast
	}
	else
	{
		checkup = payload.get("checkup", false).asBool();
	}
	w->setDisabled(disabled);
	if (checkup) craft->checkup();
}

// soldier_layout payload: { soldiers:[{ soldierId, soldierOwner, layout, personal,
// personalArmor }] }, baseId = the base whose inventory screen closed. layout and
// personal are serializeLayout() texts, each the soldier's ABSOLUTE end state
// (last-write-wins), so every machine adopts the same layouts. Without it a layout
// set on a replica never reached the host, which builds every battle.
// Separate Campaign: a player sets only their own soldiers' layouts, also at the
// other player's base, where the equipment comes from that base's stores. With the
// alternate craft equipment management the gear follows the layout between the
// soldier's craft and the stores, as vanilla's unseat / re-seat around the
// inventory screen moves it; the host's option decides and travels in the
// payload, so every machine moves the same items.
bool soldierLayoutValidate(Game* game, const Json::Value& payload, Base* base, int seat,
                           int64_t& cost, std::string& failReason)
{
	cost = 0;
	if (!base) { failReason = "base not found"; return false; }
	const Json::Value& list = payload["soldiers"];
	if (!list.isArray() || list.empty()) { failReason = "no soldiers"; return false; }
	for (const auto& entry : list)
	{
		Soldier* s = findSoldierAtBase(base, entry.get("soldierId", -1).asInt(),
			entry.get("soldierOwner", -1).asInt());
		if (!s) { failReason = "soldier not found"; return false; }
		if (!separateSoldierOwnerOk(game, s, seat))
			{ failReason = "STR_COOP_NOT_YOUR_SOLDIER"; return false; }
	}
	return true;
}

void soldierLayoutApply(Game* game, Json::Value& payload, Base* base, int /*seat*/)
{
	if (!base || !game->getSavedGame()) return;
	SavedGame* save = game->getSavedGame();
	if (isHost())
		payload["moveGear"] = save->isSeparateCoopCampaign()
			&& Options::oxceAlternateCraftEquipmentManagement
			&& save->getMonthsPassed() != -1;
	const bool moveGear = payload.get("moveGear", false).asBool();
	for (const auto& entry : payload["soldiers"])
	{
		Soldier* s = findSoldierAtBase(base, entry.get("soldierId", -1).asInt(),
			entry.get("soldierOwner", -1).asInt());
		if (!s) continue;
		std::vector<EquipmentLayoutItem*> layout =
			deserializeLayout(game, entry.get("layout", "").asString());
		const Craft* craft = s->getCraft();
		const bool atHome = craft && craft->getStatus() != "STR_OUT" && craft->getBase() == base;
		s->replaceEquipmentLayout(layout, moveGear && atHome ? base : nullptr);
		if (entry.isMember("personal"))
		{
			std::vector<EquipmentLayoutItem*> personal =
				deserializeLayout(game, entry.get("personal", "").asString());
			Collections::deleteAll(*s->getPersonalEquipmentLayout());
			s->getPersonalEquipmentLayout()->swap(personal);
			const std::string armor = entry.get("personalArmor", "").asString();
			s->setPersonalEquipmentArmor(armor.empty() ? nullptr
				: game->getMod()->getArmor(armor, false));
		}
	}
}

// base_move payload: {}. baseId = the base the mini base strip moves one place
// left (a right-click in the strip). Commands name bases by index, so the move is a host
// command that every machine applies at the same point in the apply order.
bool baseMoveValidate(Game* game, const Json::Value& /*payload*/, Base* base, int /*seat*/,
                      int64_t& cost, std::string& failReason)
{
	cost = 0;
	if (!base) { failReason = "base not found"; return false; }
	if (baseMoveTarget(game, base) < 0) { failReason = "base cannot move left"; return false; }
	return true;
}

void baseMoveApply(Game* game, Json::Value& /*payload*/, Base* base, int /*seat*/)
{
	if (!base) return;
	const int from = baseIndex(game, base);
	const int to = baseMoveTarget(game, base);
	if (from < 0 || to < 0) return;
	auto& bases = *game->getSavedGame()->getBases();
	std::swap(bases[from], bases[to]);
}

// soldier_order payload: { order:[soldierId...] }. baseId = the base. The roster
// screens show a player only their own soldiers, so move up / down reorders that
// player's soldiers among the roster places they already hold; every other
// soldier keeps its place. Ids no longer at the base are skipped and own
// soldiers the order leaves out keep their relative order after the listed ones,
// so a sack or arrival in flight cannot fail the move.
bool soldierOrderValidate(Game* /*game*/, const Json::Value& payload, Base* base, int /*seat*/,
                          int64_t& cost, std::string& failReason)
{
	cost = 0;
	if (!base) { failReason = "base not found"; return false; }
	if (!payload["order"].isArray()) { failReason = "no soldier order"; return false; }
	return true;
}

void soldierOrderApply(Game* /*game*/, Json::Value& payload, Base* base, int seat)
{
	if (!base || !payload["order"].isArray()) return;
	auto& roster = *base->getSoldiers();
	std::vector<size_t> places;
	std::vector<Soldier*> own;
	for (size_t i = 0; i < roster.size(); ++i)
		if (roster[i]->getOwnerPlayerId() == seat)
		{
			places.push_back(i);
			own.push_back(roster[i]);
		}
	std::vector<Soldier*> ordered;
	for (const auto& id : payload["order"])
		for (Soldier*& s : own)
			if (s && s->getId() == id.asInt())
			{
				ordered.push_back(s);
				s = nullptr;
				break;
			}
	for (Soldier* s : own)
		if (s) ordered.push_back(s);
	for (size_t i = 0; i < places.size(); ++i)
		roster[places[i]] = ordered[i];
}

// df_open applier (REPLICA only). The host publishes the FULL dogfight
// membership set + epoch on every change; the replica adopts it and reconciles its
// render-only windows (opens new tuples once their craft + UFO are replicated,
// closes departed ones). Payload: { epoch, dogfights:[ {craftId, craftType, ufoId,
// ufoIsAttacking} ] }. This REPLACES the J08 dogfightStartApply (initiator model).
void dfOpenApply(Game* game, Json::Value& payload, Base* /*base*/, int /*seat*/)
{
	if (connectionTCP::getHost()) return; // host owns its own DogfightState set
	GeoscapeState* gs = findGeoState(game);
	if (!gs) return; // no geoscape (sub-screen/battle): reconcile when it returns
	gs->sharedApplyDogfightMembership(payload["dogfights"], payload.get("epoch", 0).asInt());
}

// PRD-DF02: df_cmd applier (HOST only). A replica emits df_cmd on the reliable FIFO
// shared_cmd lane when any player presses a stance / weapon / disengage / self-destruct
// button on a replica-view dogfight; the host drives its authoritative DogfightState
// through the SAME lane the local UI uses, arbitrated in g_cmdQ receive-order
// (last-received-wins). Epoch guard (6): the (craftId,ufoId) must still be a live host
// dogfight, else the command is a stale pre-reshuffle order and is dropped (logged
// once). Payload: { craftId, craftType, ufoId, action, arg }. Minimize is NOT sent here
// (per-machine VIEW state, 4). The uniform shared_apply echo to replicas is a no-op
// (this applier early-returns off-host).
void dfCmdApply(Game* game, Json::Value& payload, Base* /*base*/, int /*seat*/)
{
	if (!connectionTCP::getHost()) return; // host applies; a replica ignores the echo
	GeoscapeState* gs = findGeoState(game);
	if (!gs) return;
	int craftId = payload.get("craftId", -1).asInt();
	int baseId = payload.get("baseId", -1).asInt();
	int ufoId = payload.get("ufoId", -1).asInt();
	std::string craftType = payload.get("craftType", "").asString();
	std::string action = payload.get("action", "").asString();
	int arg = payload.get("arg", -1).asInt();
	if (!gs->sharedApplyDogfightCmd(baseId, craftId, ufoId, craftType, action, arg))
	{
		static bool warned = false;
		if (!warned)
		{
			warned = true;
			Log(LOG_INFO) << "[SHARED] df_cmd dropped (stale/unknown membership): craft "
				<< craftId << " ufo " << ufoId << " action '" << action << "' (logged once)";
		}
	}
}

// ---- PRD-J10: the landing broker ---------------------------------------------
// land_prompt payload: { craftId, craftType, initiatorSeat, shade }. Host-origin
// (simAccept; applier replica-only + seat-gated), exactly like dogfight_start:
// only the seat that ORDERED the craft is asked whether to land. Battle authority
// is untouched - if the seat says yes, the HOST still generates the battle.
void landPromptApply(Game* game, Json::Value& payload, Base* base, int /*seat*/)
{
	if (connectionTCP::getHost()) return; // the host pops its own copy directly
	// Playtest: EVERY player is alerted that a craft reached its target, not only the
	// seat that commanded it. The host broadcasts land_prompt to all seats; each pops
	// the broker dialog and any player may answer (first answer wins, host-arbitrated;
	// a land_close closes the losers).
	Craft* craft = resolveOrderCraft(game, payload, base);
	if (game && game->getCoopMod() && game->getCoopMod()->isSeparateCampaign()
		&& !SeparateEcon::ownsCraft(game, craft))
		return;
	GeoscapeState* gs = findGeoState(game);
	// The dialog renders the destination's name, so a replica that has not yet
	// replicated the target (or is not on the geoscape) simply does not participate.
	// It must NOT auto-decline any more: that would cancel the landing for everyone
	// now that all seats are prompted. The host always has the target and its own
	// dialog, so the decision is never stranded.
	if (!craft || !craft->getDestination() || !gs)
	{
		return;
	}
	// Separate re-sends an unanswered prompt; keep the dialog that is already open.
	for (State* state : game->getStates())
		if (ConfirmLandingState* open = dynamic_cast<ConfirmLandingState*>(state))
			if (open->getCraft() == craft)
				return;
	// Textures are null on purpose: this dialog only ASKS. It never runs
	// checkStartingCondition or the battle generator (its broker branch submits
	// land_reply instead), and the only thing it draws from the host's world is
	// the day/night shade, which rides the payload.
	game->getCoopMod()->clearLandingResolved(craft->getId()); // fresh prompt on this seat
	gs->popup(new ConfirmLandingState(craft, nullptr, nullptr,
		payload.get("shade", 0).asInt(), true /*sharedBroker*/));
}

// land_reply payload: { craftId, craftType, yes, patrol }. Client -> host; the
// applier is HOST-ONLY (the host owns the consequence, and it is the only machine
// that can generate the authoritative battle).
void landReplyApply(Game* game, Json::Value& payload, Base* base, int /*seat*/)
{
	if (!connectionTCP::getHost()) return;
	Craft* craft = resolveOrderCraft(game, payload, base);
	GeoscapeState* gs = findGeoState(game);
	if (!craft || !gs) return;
	gs->sharedLandingReply(craft, payload.get("yes", false).asBool(),
		payload.get("patrol", false).asBool());
}
void landCloseApply(Game* game, Json::Value& payload, Base* /*base*/, int /*seat*/)
{
	if (connectionTCP::getHost()) return; // the host marked itself in sharedLandingReply
	game->getCoopMod()->markLandingResolved(payload.get("craftId", -1).asInt());
}

// patrol_prompt: a craft reached a plain patrol waypoint on the host. Replica-only: the
// client's frozen sim never ran the arrival handler, so pop the "reached destination"
// alert and clear the now-stale destination line + orphan waypoint marker.
void patrolPromptApply(Game* game, Json::Value& payload, Base* base, int /*seat*/)
{
	if (connectionTCP::getHost()) return; // the host handled its own copy in time5Seconds
	Craft* craft = resolveOrderCraft(game, payload, base);
	GeoscapeState* gs = findGeoState(game);
	if (!craft || !gs) return;
	gs->clientCraftReachedWaypoint(craft);
}

// base_damaged payload: { ufoId, missileHit, facilities:[{type,x,y,buildTime}] }.
// Host-origin, replica-only apply.
//
// A missile-armed UFO that survives the base's defences bombards the base instead of
// landing: Base::damageFacilities() destroys/replaces facilities and the base SURVIVES
// (no battle at all). That runs in handleBaseDefense, which only the host reaches (the
// replica's geoscape sim is frozen), and BaseDestroyedState::btnOkClick returns early for
// a partial destruction - so nothing was ever broadcast and the client's copy of the ONE
// shared base kept the facilities the host had just lost.
//
// damageFacilities() is RNG-driven (WeightedOptions::choose), so a replica cannot re-roll
// it; the host sends the resulting layout as an ABSOLUTE end-state and the replica adopts
// it verbatim (same idiom as the GAP-5 equip commands).
void baseDamagedApply(Game* game, Json::Value& payload, Base* base, int /*seat*/)
{
	if (connectionTCP::getHost()) return; // the host already applied its own roll
	if (!base) return;
	Mod* mod = game->getMod();
	SavedGame* save = game->getSavedGame();
	if (!mod || !save) return;

	// Adopt the host's post-damage facility layout wholesale.
	auto* facs = base->getFacilities();
	for (auto* f : *facs) delete f;
	facs->clear();
	const Json::Value& jf = payload["facilities"];
	for (Json::ArrayIndex i = 0; i < jf.size(); ++i)
	{
		RuleBaseFacility* rule = mod->getBaseFacility(jf[i].get("type", "").asString(), false);
		if (!rule) continue;
		BaseFacility* f = new BaseFacility(rule, base);
		f->setX(jf[i].get("x", 0).asInt());
		f->setY(jf[i].get("y", 0).asInt());
		f->setBuildTime(jf[i].get("buildTime", 0).asInt());
		facs->push_back(f);
	}
	save->stopHuntingXcomCrafts(base);
	base->cleanupDefenses(true);

	// Same "base damaged but survived" dialog the host shows. Safe to pop the real one:
	// its OK handler returns early for a partial destruction and never erases the base.
	// Separate: only the base owner gets it.
	GeoscapeState* gs = findGeoState(game);
	if (!gs || !SeparateEcon::showBaseNotification(game, base)) return;
	Ufo* ufo = nullptr;
	const int ufoId = payload.get("ufoId", -1).asInt();
	for (auto* u : *save->getUfos())
		if (u->getId() == ufoId) { ufo = u; break; }
	gs->popup(new BaseDestroyedState(base, ufo, true, true));
}

// alien_base_found payload carries the complete target.  A freshly spawned base
// does not exist in a frozen replica yet, so discovery must be able to create it
// before applying the flag and popup.
// X-Com discovering an alien base is a shared-world MUTATION (setDiscovered), not just an
// alert, so it must not be rolled twice. The replica's time1MonthCoop used to run its OWN
// RNG::percent(chanceToDetectAlienBaseEachMonth) and pick its own base, so host and client
// could disagree about which base (if any) was found. The host now rolls alone and names
// the winner here.
void alienBaseFoundApply(Game* game, Json::Value& payload, Base* /*base*/, int /*seat*/)
{
	if (connectionTCP::getHost()) return; // the host already applied its own roll
	SavedGame* save = game->getSavedGame();
	GeoscapeState* gs = findGeoState(game);
	if (!save || !gs) return;
	const int id = payload.get("alienBaseId", -1).asInt();
	AlienBase* found = nullptr;
	for (auto* ab : *save->getAlienBases())
	{
		if (ab->getId() == id)
		{
			found = ab;
			break;
		}
	}
	if (!found)
	{
		const std::string deploymentName = payload.get("deployment", "").asString();
		AlienDeployment* deployment = game->getMod()->getDeployment(deploymentName, false);
		if (!deployment) return;
		found = new AlienBase(deployment, payload.get("startMonth", 0).asInt());
		found->setId(id);
		found->_coop_alienbase_id = payload.get("coopId", 0).asInt();
		found->_coop = true;
		save->getAlienBases()->push_back(found);
	}
	found->setLongitude(payload.get("lon", 0.0).asDouble());
	found->setLatitude(payload.get("lat", 0.0).asDouble());
	found->setPactCountry(payload.get("pactCountry", "").asString());
	found->setAlienRace(payload.get("race", "").asString());
	found->setOwnerPlayerName(payload.get("ownerPlayerName", "").asString());
	found->setDiscovered(true);
	gs->popup(new AlienBaseState(found, gs));
}

// ---- generic informational-alert replication --------------------------------
// In SHARED only the host runs the geoscape sim, so EVERY informational popup it raises
// (UFO lost, low fuel, items arrived, new research possibilities, training finished, ...)
// is invisible to the clients. Rather than a bespoke shared_cmd per dialog, the host
// broadcasts ONE `alert` command naming the dialog class plus the ids/rule names needed to
// rebuild it, and this replica-only applier reconstructs and pops the real dialog.
// payload: { cls, msg, craftId, baseIdx, names[], ids[], flag }
//
// Only informational dialogs belong here - anything that also MUTATES the shared world
// (base defense, alien base spawns) needs real state mirroring, not just a popup.
static Craft* alertCraft(Game* game, int craftId)
{
	if (craftId < 0 || !game->getSavedGame()) return nullptr;
	for (auto* b : *game->getSavedGame()->getBases())
		for (auto* c : *b->getCrafts())
			if (c->getId() == craftId) return c;
	return nullptr;
}

void alertApply(Game* game, Json::Value& payload, Base* base, int /*seat*/)
{
	if (connectionTCP::getHost()) return; // the host already popped its own copy
	GeoscapeState* gs = findGeoState(game);
	if (!gs || !game->getSavedGame()) return;
	Mod* mod = game->getMod();
	const std::string cls = payload.get("cls", "").asString();
	const std::string msg = payload.isMember("text") ? textRender(game, payload["text"]) : payload.get("msg", "").asString(); // this machine's language


	std::vector<std::string> names;
	const Json::Value& jn = payload["names"];
	for (Json::ArrayIndex i = 0; i < jn.size(); ++i) names.push_back(jn[i].asString());

	// `base` is routed by baseIdx already; fall back to the first base for dialogs that
	// need one but were raised without a meaningful index.
	if (!base && !game->getSavedGame()->getBases()->empty())
		base = game->getSavedGame()->getBases()->front();

	const bool researchUnlockAlert = cls == "ResearchRequiredState"
		|| cls == "NewPossibleResearchState"
		|| cls == "NewPossibleManufactureState"
		|| cls == "NewPossiblePurchaseState"
		|| cls == "NewPossibleCraftState"
		|| cls == "NewPossibleFacilityState";
	if (researchUnlockAlert && !SeparateEcon::showResearchCompletion(game, base))
		return;

	if (cls == "UfoLostState")
	{
		gs->popup(new UfoLostState(msg));
	}
	else if (cls == "CraftErrorState")
	{
		// flag = a base-scoped error (rearm): Separate shows it to the base owner only.
		if (payload.get("flag", false).asBool() && !SeparateEcon::showBaseNotification(game, base))
			return;
		// player = a notice for one player (hostPlayerNotice: the month-end
		// economy warning); every other machine ignores it.
		if (payload.isMember("player")
			&& payload["player"].asString() != connectionTCP::seatName(connectionTCP::localSeat()))
			return;
		gs->popup(new CraftErrorState(gs, msg));
	}
	else if (cls == "DogfightErrorState")
	{
		Craft* c = alertCraft(game, payload.get("craftId", -1).asInt());
		if (c) gs->popup(new DogfightErrorState(c, msg));
	}
	else if (cls == "LowFuelState")
	{
		Craft* c = alertCraft(game, payload.get("craftId", -1).asInt());
		if (c) gs->popup(new LowFuelState(c, gs));
	}
	else if (cls == "ItemsArrivingState")
	{
		const Json::Value& jr = payload["rows"];
		if (jr.isArray() && !jr.empty())
		{
			std::vector<ArrivalRow> rows;
			for (Json::ArrayIndex i = 0; i < jr.size(); ++i)
			{
				ArrivalRow row;
				row.type = jr[i].get("type", 0).asInt();
				row.name = jr[i].isMember("text") ? textRender(game, jr[i]["text"]) : jr[i].get("name", "").asString();
				row.qty = jr[i].get("qty", 0).asInt();
				row.base = jr[i].get("base", "").asString();
				row.baseIdx = jr[i].get("baseIdx", -1).asInt();
				row.ownerSeat = jr[i].get("ownerSeat", -1).asInt();
				row.ownerPlayerName = jr[i].get("ownerPlayerName", "").asString();
				if (row.ownerPlayerName.empty() || !game->getCoopMod()->isSeparateCampaign()
					|| row.ownerPlayerName == connectionTCP::seatName(connectionTCP::localSeat()))
					rows.push_back(row);
			}
			if (!rows.empty()) gs->popup(new ItemsArrivingState(gs, rows));
		}
	}
	else if (cls == "SeparateStorageExceeded")
	{
		// The host simulates storage for every Separate base, but only the base
		// owner may receive and resolve this mandatory sell dialog.
		if (!base || !game->getCoopMod()->isSeparateCampaign()
			|| !SeparateEcon::showBaseNotification(game, base))
			return;
		auto* itf = mod->getInterface("geoscape");
		gs->popup(new ErrorMessageState(
			game->getLanguage()->getString("STR_STORAGE_EXCEEDED").arg(base->getName()),
			game->getScreen()->getPalette(), itf->getElement("errorMessage")->color,
			"BACK13.SCR", itf->getElement("errorPalette")->color));
		gs->popup(new SellState(base, nullptr));
	}
	else if (cls == "ResearchRequiredState")
	{
		if (RuleItem* it = mod->getItem(msg, false)) gs->popup(new ResearchRequiredState(it));
	}
	else if (cls == "GeoscapeEventState")
	{
		if (const RuleEvent* ev = mod->getEvent(msg, false))
		{
			CoopEventPicks none; // the generic lane only displays (empty picks, own language); no world write
			GeoscapeEventState::coopArmDisplay(&none);
			gs->popup(new GeoscapeEventState(*ev));
		}
	}
	else if (cls == "NewPossibleResearchState")
	{
		std::vector<RuleResearch*> v;
		for (const auto& n : names) if (auto* r = mod->getResearch(n, false)) v.push_back(r);
		if (base) gs->popup(new NewPossibleResearchState(base, v));
	}
	else if (cls == "NewPossibleManufactureState")
	{
		std::vector<RuleManufacture*> v;
		for (const auto& n : names) if (auto* r = mod->getManufacture(n, false)) v.push_back(r);
		if (base) gs->popup(new NewPossibleManufactureState(base, v));
	}
	else if (cls == "NewPossiblePurchaseState")
	{
		std::vector<RuleItem*> v;
		for (const auto& n : names) if (auto* r = mod->getItem(n, false)) v.push_back(r);
		if (base) gs->popup(new NewPossiblePurchaseState(base, v));
	}
	else if (cls == "NewPossibleCraftState")
	{
		std::vector<RuleCraft*> v;
		for (const auto& n : names) if (auto* r = mod->getCraft(n, false)) v.push_back(r);
		if (base) gs->popup(new NewPossibleCraftState(base, v));
	}
	else if (cls == "NewPossibleFacilityState")
	{
		std::vector<RuleBaseFacility*> v;
		for (const auto& n : names) if (auto* r = mod->getBaseFacility(n, false)) v.push_back(r);
		if (base) gs->popup(new NewPossibleFacilityState(base, gs->getGlobe(), v));
	}
	else if (cls == "TrainingFinishedState")
	{
		std::vector<Soldier*> v;
		const Json::Value& ids = payload["ids"];
		if (base && SeparateEcon::showBaseNotification(game, base))
		{
			for (Json::ArrayIndex i = 0; i < ids.size(); ++i)
				for (auto* s : *base->getSoldiers())
					if (s->getId() == ids[i].asInt()) v.push_back(s);
			if (!v.empty())
				gs->popup(new TrainingFinishedState(base, v, payload.get("flag", false).asBool()));
		}
	}
}

// ---- geo_event - the replica side ------------------------------------------------------
// A GeoscapeEventState's ctor runs eventLogic, which writes the world with the host's dice. Only the host runs it; the
// host-origin geo_event carries its exact result (hostGeoEvent) and the window's picks as ids. The replica adopts the
// result absolutely and draws a display-only window in its own language - it never re-runs eventLogic.
struct QueuedEventWindow { const RuleEvent* rule; CoopEventPicks picks; };
std::vector<QueuedEventWindow> g_eventWindows; // replica: windows waiting for the geoscape

// The ONE place a geo_event window is built: popped on the live geoscape, else queued until GeoscapeState::init
// (a SHARED client's debriefing OK replaces its stack with a new GeoscapeState, which would drop a queued popup).
void showEventWindow(Game* game, GeoscapeState* gs, const RuleEvent& rule, const CoopEventPicks& picks)
{
	bool debrief = false;
	for (auto* st : game->getStates()) debrief = debrief || dynamic_cast<DebriefingState*>(st) != nullptr;
	if (!gs || debrief)
	{
		g_eventWindows.push_back(QueuedEventWindow{ &rule, picks });
		Log(LOG_INFO) << "[SHARED] geo_event " << rule.getName() << ": window queued until the geoscape returns ("
			<< g_eventWindows.size() << " pending)";
		return;
	}
	GeoscapeEventState::coopArmDisplay(&picks); // consumed by the ctor below: the window draws these picks
	gs->popup(new GeoscapeEventState(rule));
}

// geo_event payload (hostGeoEvent): { event, picks {region, city, rows [[item, qty]], research, bonus}, transfers [yaml],
// crafts [yaml], store [{base, items}], craftItems [{base, craft, id, items}], research {added, removed [{name,
// popped}], status {name: value}, diary [yaml], projects [{base, names}]}, score, regions {type: value}, ids {name:
// value} }. Funds are the packet's (processApply adopted them first).
void geoEventApply(Game* game, Json::Value& payload, Base* /*base*/, int /*seat*/)
{
	if (connectionTCP::getHost()) return;
	SavedGame* save = game->getSavedGame();
	Mod* mod = game->getMod();
	const RuleEvent* rule = mod ? mod->getEvent(payload.get("event", "").asString(), false) : nullptr;
	if (!save || !rule || save->getBases()->empty()) return;
	auto* bases = save->getBases();
	Base* hq = bases->front();
	auto baseAt = [&](const Json::Value& v) -> Base* { const int i = v.asInt(); return i >= 0 && i < (int)bases->size() ? (*bases)[i] : nullptr; };

	// 1) research: obsolete projects (3j), discovered, statuses, popped flags, diary - the host's state, no dice
	const Json::Value& rs = payload["research"];
	for (const auto& pr : rs["projects"])
	{
		Base* b = baseAt(pr["base"]);
		if (!b) continue;
		std::set<std::string> keep;
		for (const auto& n : pr["names"]) keep.insert(n.asString());
		std::vector<ResearchProject*> gone;
		for (auto* rp : b->getResearch()) if (!keep.count(rp->getRules()->getName())) gone.push_back(rp);
		for (auto* rp : gone) b->removeResearch(rp);
	}
	for (const auto& e : rs["added"])
		if (const RuleResearch* r = mod->getResearch(e["name"].asString(), false))
			if (!save->isResearched(r, false)) save->addFinishedResearchSimple(r);
	for (const auto& e : rs["removed"])
		if (const RuleResearch* r = mod->getResearch(e["name"].asString(), false)) save->removeDiscoveredResearch(r);
	for (const auto& k : rs["status"].getMemberNames()) save->setResearchRuleStatus(k, rs["status"][k].asInt());
	for (const Json::Value* list : { &rs["added"], &rs["removed"] })
		for (const auto& e : *list)
			if (const RuleResearch* r = mod->getResearch(e["name"].asString(), false))
			{
				if (e["popped"].asBool()) save->addPoppedResearch(r);
				else save->removePoppedResearch(r);
			}
	for (const auto& y : rs["diary"])
	{
		YAML::YamlRootNodeReader reader(YAML::YamlString{ y.asString() }, "geo_event diary");
		auto* entry = new ResearchDiaryEntry(nullptr);
		entry->load(reader["n"], mod);
		save->addResearchDiaryEntry(entry);
	}

	// 2) the host's new hq transfers and crafts, as their own YAML (soldiers, ids and names are the host's)
	for (const auto& y : payload["transfers"])
	{
		YAML::YamlRootNodeReader reader(YAML::YamlString{ y.asString() }, "geo_event transfer");
		auto* t = new Transfer(0);
		if (t->load(reader["n"], hq, mod, save)) hq->getTransfers()->push_back(t); // false: load already deleted it
	}
	for (const auto& y : payload["crafts"])
	{
		YAML::YamlRootNodeReader reader(YAML::YamlString{ y.asString() }, "geo_event craft");
		const RuleCraft* cr = mod->getCraft(reader["n"]["type"].readVal<std::string>(), false);
		if (!cr) continue;
		auto* c = new Craft(cr, hq);
		c->load(reader["n"], mod->getScriptGlobal(), mod, save);
		hq->getCrafts()->push_back(c);
	}

	// 3) stores and pre-existing crafts' items: each listed container is set to the host's map exactly
	auto setItems = [&](ItemContainer* ic, const Json::Value& items)
	{
		ic->clear();
		for (const auto& k : items.getMemberNames())
			if (RuleItem* ri = mod->getItem(k, false)) ic->addItem(ri, items[k].asInt());
	};
	for (const auto& s : payload["store"])
		if (Base* b = baseAt(s["base"])) setItems(b->getStorageItems(), s["items"]);
	for (const auto& ci : payload["craftItems"])
		if (Base* b = baseAt(ci["base"]))
			for (auto* c : *b->getCrafts())
				if (craftKey(c) == craftKey(ci["craft"].asString(), ci["id"].asInt())) setItems(c->getItems(), ci["items"]);

	// 4) score, region activity, id counters (stepped with getId, as prod_done keeps craft ids in step)
	if (payload.isMember("score") && !save->getResearchScores().empty())
		save->getResearchScores().back() = payload["score"].asInt();
	const Json::Value& regions = payload["regions"];
	for (auto* rg : *save->getRegions())
		if (regions.isMember(rg->getRules()->getType()) && !rg->getActivityXcom().empty())
			rg->getActivityXcom().back() = regions[rg->getRules()->getType()].asInt();
	const std::map<std::string, int>& ids = save->getAllIds();
	for (const auto& k : payload["ids"].getMemberNames())
		while (ids.find(k) == ids.end() || ids.at(k) < payload["ids"][k].asInt()) save->getId(k);

	// 5) the window: the host's picks, drawn by this machine in its own language
	CoopEventPicks picks;
	const Json::Value& pk = payload["picks"];
	picks.region = pk.get("region", "").asString();
	picks.city = pk.get("city", -1).asInt();
	for (const auto& r : pk["rows"]) picks.rows.push_back(std::make_pair(r[0u].asString(), r[1u].asInt()));
	picks.research = pk.get("research", "").asString();
	picks.bonus = pk.get("bonus", "").asString();
	showEventWindow(game, findGeoState(game), *rule, picks);
}

// PRD-DF01: the J08 host-applies-reported-result path is GONE. The host now
// simulates every SHARED dogfight in its own DogfightState::update, which is the
// SINGLE home for the UFO-downed consequences (country/region score + the
// retaliation roll) - so hostRollRetaliation + dogfightResultApply are deleted
// to avoid a double-roll. The world outcome reaches replicas via the geo
// position snapshot (UFO CRASHED/crashId, craft damage/fuel/ammo).
// research_done payload: { research, bonus, newResearch } (rule names; bonus /
// newResearch may be "").
void researchDoneApply(Game* game, Json::Value& payload, Base* base, int /*seat*/)
{
	if (connectionTCP::getHost()) return; // host already applied in time1Day
	if (!base) return;
	SavedGame* save = game->getSavedGame();
	Mod* mod = game->getMod();
	if (!save || !mod) return;

	const std::string rName = payload.get("research", "").asString();
	RuleResearch* research = mod->getResearch(rName, false);
	if (!research) return;
	const std::string bName = payload.get("bonus", "").asString();
	RuleResearch* bonus = bName.empty() ? nullptr : mod->getResearch(bName, false);
	// the BASE / FREE_FROM diary lines exactly as the host's time1Day writes them (GeoscapeState
	// addResearchDiaryEntryForBase), interleaved with the adds below in the host's order.
	const size_t h17Diary0 = save->getResearchDiary().size();
	auto h17Diary = [&](const RuleResearch* discovered, DiscoverySourceType sourceType, const RuleResearch* sourceResearch)
	{
		if (save->isResearched(discovered) || save->isResearchRuleStatusDisabled(discovered->getName())) return;
		ResearchDiaryEntry* entry = new ResearchDiaryEntry(discovered);
		entry->setDate(save->getTime());
		entry->source.type = sourceType;
		if (sourceType == DiscoverySourceType::BASE) entry->source.name = base->getName();
		else { entry->source.research = sourceResearch; entry->source.name = sourceResearch->getName(); } // FREE_FROM
		save->addResearchDiaryEntry(entry);
	};

	// Remove the base's matching ResearchProject and free its scientists, exactly
	// as the host's time1Day did. Mark it finished first so removeResearch() does
	// not take the "cancelled research" branch and refund the needed item (the
	// replica's frozen project never stepped, so it looks unfinished).
	for (auto* proj : base->getResearch())
	{
		if (proj->getRules()->getName() == rName)
		{
			proj->setSpent(proj->getCost());
			base->removeResearch(proj);
			break;
		}
	}
	// A finished interrogation put the alien's corpse back in the host's stores
	// (time1Day 3b, the host's retainCorpses option); keep exactly that corpse.
	if (const RuleItem* corpse = mod->getItem(payload.get("corpse", "").asString(), false))
		base->getStorageItems()->addItem(corpse);

	// Add the discovered topic(s). The host already selected the getOneFree
	// (RNG) and passed it as `bonus`; addFinishedResearch itself is deterministic,
	// so applying the host's exact choices keeps the replica identical.
	h17Diary(research, DiscoverySourceType::BASE, nullptr); // GS 3bb, the topic and its lookup
	if (RuleResearch* lr = mod->getResearch(research->getLookup(), true))
		h17Diary(lr, DiscoverySourceType::BASE, nullptr);
	if (bonus)
	{
		h17Diary(bonus, DiscoverySourceType::FREE_FROM, research); // GS 3c, the bonus and its lookup
		save->addFinishedResearch(bonus, mod, base);
		if (!bonus->getLookup().empty())
		{
			h17Diary(mod->getResearch(bonus->getLookup(), true), DiscoverySourceType::FREE_FROM, research);
			save->addFinishedResearch(mod->getResearch(bonus->getLookup(), true), mod, base);
		}
	}
	save->addFinishedResearch(research, mod, base);
	if (!research->getLookup().empty())
		save->addFinishedResearch(mod->getResearch(research->getLookup(), true), mod, base);
	// every diary line this apply appended (BASE, FREE_FROM, addFinishedResearch's FREE_AFTER)
	// carries the host's date, so a replica clock behind the host's midnight cannot date them differently.
	const Json::Value h17Date = payload.get("date", Json::Value());
	if (h17Date.isArray() && h17Date.size() == 3)
		for (size_t i = h17Diary0; i < save->getResearchDiary().size(); ++i)
		{
			ResearchDiaryEntry* e = save->getResearchDiary()[i];
			e->year = h17Date[0u].asUInt(); e->month = h17Date[1u].asUInt(); e->day = h17Date[2u].asUInt();
		}

	// Mirror the host popup (coop=true -> the ctor does NOT re-broadcast).
	const std::string nrName = payload.get("newResearch", "").asString();
	const RuleResearch* newResearch = nrName.empty() ? nullptr : mod->getResearch(nrName, false);
	if (connectionTCP::campaignEnded()) return; // coop: the host's window died with its setState
	if (SeparateEcon::showResearchCompletion(game, base))
		game->pushState(new ResearchCompleteState(newResearch, bonus, research, base, true));
	// Separate: a non-ending research cutscene plays for the research owner only
	// (the host plays its own; an ending arrives as faction_campaign_end).
	if (game->getCoopMod() && game->getCoopMod()->isSeparateCampaign()
		&& SeparateEcon::showBaseNotification(game, base))
		for (const RuleResearch* topic : { research, bonus })
		{
			if (!topic || topic->getCutscene().empty()) continue;
			const RuleVideo* video = mod->getVideo(topic->getCutscene(), false);
			if (!video || video->getWinGame() || video->getLoseGame()) continue;
			game->getCoopMod()->allow_cutscene = false;
			game->pushState(new CutsceneState(topic->getCutscene()));
		}
}

// world_extras: defined beside the world checksum terms it shares (hostWorldExtras).
void worldExtrasApply(Game* game, Json::Value& payload, Base* base, int seat);

// research_effects payload: { removed: [ {baseIdx, research, refund} ],
// transfers: [ {item, qty, hours, owner} ] }; baseId = the researching base.
// The host's handlePrimaryResearchSideEffects results for one base's completed
// topics (hostResearchSideEffects), sent after that base's research_done results.
void researchEffectsApply(Game* game, Json::Value& payload, Base* base, int /*seat*/)
{
	if (connectionTCP::getHost()) return; // host already applied in time1Day
	Mod* mod = game->getMod();
	if (!mod) return;
	for (const auto& r : payload["removed"])
	{
		Base* from = resolveBase(game, r.get("baseIdx", -1).asInt());
		ResearchProject* proj = from
			? findResearchProject(from, r.get("research", "").asString()) : nullptr;
		if (!proj) continue;
		// The host decided the needed-item refund from its own progress. Mark the
		// copy finished so removeResearch() does not decide again, then refund
		// exactly as the host did.
		proj->setSpent(proj->getCost());
		const RuleItem* needed = proj->getRules()->getNeededItem();
		if (r.get("refund", false).asBool() && needed)
			from->getStorageItems()->addItem(needed, 1);
		from->removeResearch(proj);
	}
	if (!base) return;
	for (const auto& s : payload["transfers"])
	{
		const RuleItem* item = mod->getItem(s.get("item", "").asString(), false);
		if (!item) continue;
		Transfer* t = new Transfer(s.get("hours", 1).asInt());
		t->setOwnerPlayerName(s.get("owner", "").asString());
		t->setItems(item, s.get("qty", 1).asInt());
		base->getTransfers()->push_back(t);
	}
}

// research_fx payload (hostResearchFx): { removed [{base, name}], stores [{base,
// items {itemType: qty}}], transfers [{base, item, qty, hours}], ids {name: value} } - the host's research-completion side
// effects (3b corpse, 3j obsolete projects + refunds, 3k spawned items, 3m counters), adopted absolutely. Replica only:
// it runs none of the host's side-effect code (no RNG, no spawned event; 3l stays host-only).
void researchFxApply(Game* game, Json::Value& payload, Base* /*base*/, int /*seat*/)
{
	if (connectionTCP::getHost()) return;
	SavedGame* save = game->getSavedGame();
	Mod* mod = game->getMod();
	if (!save || !mod) return;
	for (const auto& r : payload["removed"])
		if (Base* b = resolveBase(game, r.get("base", -1).asInt()))
			for (auto* rp : b->getResearch())
				if (rp->getRules()->getName() == r.get("name", "").asString())
				{
					rp->setSpent(rp->getCost()); // as finished: no replica-side refund (the host's rides `stores`)
					b->removeResearch(rp);
					break;
				}
	for (const auto& st : payload["stores"]) // the host's quantities of every changed item
		if (Base* b = resolveBase(game, st.get("base", -1).asInt()))
			for (const auto& k : st["items"].getMemberNames())
				if (const RuleItem* ri = mod->getItem(k, false))
				{
					const int d = st["items"][k].asInt() - b->getStorageItems()->getItem(ri);
					if (d > 0) b->getStorageItems()->addItem(ri, d);
					else if (d < 0) b->getStorageItems()->removeItem(ri, -d);
				}
	for (const auto& t : payload["transfers"]) // delivered by the host's transfer_arrived (same queue, after this)
	{
		Base* b = resolveBase(game, t.get("base", -1).asInt());
		const RuleItem* ri = mod->getItem(t.get("item", "").asString(), false);
		if (!b || !ri) continue;
		Transfer* tr = new Transfer(t.get("hours", 1).asInt());
		tr->setItems(ri, t.get("qty", 1).asInt());
		b->getTransfers()->push_back(tr);
	}
	const std::map<std::string, int>& idsNow = save->getAllIds();
	for (const auto& k : payload["ids"].getMemberNames())
	{
		const int want = payload["ids"][k].asInt();
		if (k.empty()) continue;
		if (!idsNow.count(k)) // absent: an increase creates 2, a decrease creates 1
		{
			if (want > 1) save->increaseCustomCounter(k);
			else save->decreaseCustomCounter(k);
		}
		while (idsNow.at(k) < want) save->increaseCustomCounter(k);
		while (idsNow.at(k) > want && idsNow.at(k) > 1) save->decreaseCustomCounter(k);
	}
}

// research_grant (hostResearchGrant): { source, research {added / removed [{name, popped}], status
// {name: value}, diary [yaml], projects [{base, names}]}, score?, ids {name: value}, articles [id] } - adopted absolutely (geoEventApply step 1's twin), then the host's arc articles open in order. Replica only; no RNG, no mission interruption.
void researchGrantApply(Game* game, Json::Value& payload, Base* /*base*/, int /*seat*/)
{
	if (connectionTCP::getHost()) return;
	SavedGame* save = game->getSavedGame();
	Mod* mod = game->getMod();
	if (!save || !mod) return;
	auto* bases = save->getBases();
	const Json::Value& rs = payload["research"];
	for (const auto& pr : rs["projects"])
	{
		const int bi = pr["base"].asInt();
		if (bi < 0 || bi >= (int)bases->size()) continue;
		Base* b = (*bases)[bi];
		std::set<std::string> keep;
		for (const auto& n : pr["names"]) keep.insert(n.asString());
		std::vector<ResearchProject*> gone;
		for (auto* rp : b->getResearch()) if (!keep.count(rp->getRules()->getName())) gone.push_back(rp);
		for (auto* rp : gone) { rp->setSpent(rp->getCost()); b->removeResearch(rp); } // as finished: no replica-side refund
	}
	for (const auto& e : rs["added"])
		if (const RuleResearch* r = mod->getResearch(e["name"].asString(), false))
			if (!save->isResearched(r, false)) save->addFinishedResearchSimple(r);
	for (const auto& e : rs["removed"])
		if (const RuleResearch* r = mod->getResearch(e["name"].asString(), false)) save->removeDiscoveredResearch(r);
	for (const auto& k : rs["status"].getMemberNames()) save->setResearchRuleStatus(k, rs["status"][k].asInt());
	for (const Json::Value* list : { &rs["added"], &rs["removed"] })
		for (const auto& e : *list)
			if (const RuleResearch* r = mod->getResearch(e["name"].asString(), false))
			{
				if (e["popped"].asBool()) save->addPoppedResearch(r);
				else save->removePoppedResearch(r);
			}
	for (const auto& y : rs["diary"])
	{
		YAML::YamlRootNodeReader reader(YAML::YamlString{ y.asString() }, "research_grant diary");
		auto* entry = new ResearchDiaryEntry(nullptr);
		entry->load(reader["n"], mod);
		save->addResearchDiaryEntry(entry);
	}
	if (payload.isMember("score") && !save->getResearchScores().empty())
		save->getResearchScores().back() = payload["score"].asInt();
	const std::map<std::string, int>& idsNow = save->getAllIds();
	for (const auto& k : payload["ids"].getMemberNames())
	{
		const int want = payload["ids"][k].asInt();
		if (k.empty()) continue;
		if (!idsNow.count(k)) // absent: an increase creates 2, a decrease creates 1 (SG :2379-2417)
		{
			if (want > 1) save->increaseCustomCounter(k);
			else save->decreaseCustomCounter(k);
		}
		while (idsNow.at(k) < want) save->increaseCustomCounter(k);
		while (idsNow.at(k) > want && idsNow.at(k) > 1) save->decreaseCustomCounter(k);
	}
	for (const auto& a : payload["articles"])
		Ufopaedia::openArticle(game, a.asString());
}

// fac_done payload: { x, y, type }.
void facDoneApply(Game* game, Json::Value& payload, Base* base, int /*seat*/)
{
	if (connectionTCP::getHost()) return;
	if (!base) return;
	int x = payload.get("x", -1).asInt();
	int y = payload.get("y", -1).asInt();
	for (auto* fac : *base->getFacilities())
	{
		if (fac->getX() == x && fac->getY() == y && fac->getBuildTime() > 0)
		{
			fac->setBuildTime(0);
			GeoscapeState* gs = findGeoState(game);
			if (gs && SeparateEcon::showBaseNotification(game, base))
				game->pushState(new ProductionCompleteState(
					base, game->getLanguage()->getString(payload.get("type", "").asString()),
					gs, PROGRESS_CONSTRUCTION));
			break;
		}
	}
}

// prod_done payload: { manufacture, units, progress, sell, craftIds, final }.
// units = what the host's step made this hour; final = the batch is done (an
// older host sends only the finished batch, so a missing flag means done).
void prodDoneApply(Game* game, Json::Value& payload, Base* base, int /*seat*/)
{
	if (connectionTCP::getHost()) return;
	if (!base) return;
	SavedGame* save = game->getSavedGame();
	Mod* mod = game->getMod();
	if (!save || !mod) return;

	const std::string mName = payload.get("manufacture", "").asString();
	int units = payload.get("units", 0).asInt();
	const bool batchDone = payload.get("final", true).asBool();
	// GAP-6b: the host Production's SELL flag. When set, Production::step() credited
	// funds and added NOTHING to stores for the produced items; the authoritative
	// funds ride this shared_apply as usual, so the replica must skip the storage add
	// or its item count drifts ABOVE the host. The sell branch lives inside the
	// NON-craft arm of Production::step(), so a produced CRAFT is never sold - the
	// craft materialization below stays unconditional.
	bool sell = payload.get("sell", false).asBool();
	RuleManufacture* rule = mod->getManufacture(mName, false);
	if (!rule) return;

	// SHARED: every unit, sold or made, already reached this replica by prod_fx in the hour the host made it;
	// prod_done only removes the production and shows the window. Separate: prod_done carries the units.
	if (save->isSeparateCoopCampaign())
	{
		// Materialize the deterministic output (items + crafts) where the host's
		// Production::step() put it: the stores and the hangar, or a transfer when
		// the manufacture ships its output (transferTimes: items first, crafts
		// third). Random production is host-RNG and NOT reconstructed here
		// (documented limitation); the next shared_apply / checksum surfaces any
		// resulting drift. Spawned persons are rebuilt below.
		const std::vector<int>& shipHours = rule->getTransferTimes();
		const int itemHours = std::max(0, shipHours.empty() ? 0 : shipHours.front());
		const int craftHours = std::max(0, shipHours.size() < 3 ? 0 : shipHours.at(2));
		if (!sell && units > 0)
		{
			if (itemHours > 0)
			{
				for (int u = 0; u < units; ++u)
					for (const auto& it : rule->getProducedItems())
					{
						Transfer* t = new Transfer(itemHours);
						t->setItems(it.first, it.second);
						base->getTransfers()->push_back(t);
					}
			}
			else
			{
				for (const auto& it : rule->getProducedItems())
					base->getStorageItems()->addItem(it.first, it.second * units);
			}
		}
		if (const RuleCraft* craftRule = rule->getProducedCraft())
		{
			const std::string& craftType = craftRule->getType();
			auto build = [&](int craftId)
			{
				Craft* craft = new Craft(const_cast<RuleCraft*>(craftRule), base, craftId);
				craft->initFixedWeapons(mod);
				craft->checkup();
				if (craftHours > 0)
				{
					Transfer* t = new Transfer(craftHours);
					t->setCraft(craft);
					base->getTransfers()->push_back(t);
				}
				else
				{
					base->getCrafts()->push_back(craft);
				}
			};
			const Json::Value& craftIds = payload["craftIds"];
			if (craftIds.isArray())
			{
				// The host's ids, never this machine's counter. A craft the replica
				// already holds (it arrived in a world stream after the host built
				// it) is not built twice.
				for (const auto& jid : craftIds)
				{
					const int craftId = jid.asInt();
					adoptCraftId(save, craftType, craftId);
					if (!baseHasCraft(base, craftId, craftType))
						build(craftId);
				}
			}
			else
			{
				// Older host: no ids travel, mint in counter lock-step as before.
				for (int c = 0; c < units; ++c)
					build(save->getId(craftType));
			}
		}

		// Spawned persons (spawnedPersonType) travel as on the host: one transfer
		// per unit with the rule's personnel transfer time. A scientist or engineer
		// is a count; a soldier is the host's own (id, name, stats, owner), never one
		// this machine rolls. A soldier the replica already holds (a world stream
		// after the host spawned it) is not added twice.
		const std::string& person = rule->getSpawnedPersonType();
		if (!person.empty())
		{
			const int personHours = std::max(1, shipHours.size() < 2 ? 24 : shipHours.at(1));
			if (person == "STR_SCIENTIST" || person == "STR_ENGINEER")
			{
				for (int u = 0; u < units; ++u)
				{
					Transfer* t = new Transfer(personHours);
					if (person == "STR_SCIENTIST") t->setScientists(1);
					else t->setEngineers(1);
					base->getTransfers()->push_back(t);
				}
			}
			else
			{
				auto held = [&](int id)
				{
					if (findSoldier(base, id)) return true;
					for (auto* t : *base->getTransfers())
						if (t->getType() == TRANSFER_SOLDIER && t->getSoldier()
							&& t->getSoldier()->getId() == id) return true;
					return false;
				};
				for (const auto& yaml : payload["soldiers"])
				{
					Soldier* s = deserializeSoldier(game, yaml.asString());
					if (!s) continue;
					if (held(s->getId())) { delete s; continue; }
					Transfer* t = new Transfer(personHours);
					t->setSoldier(s);
					base->getTransfers()->push_back(t);
				}
			}
		}
	}

	// A unit inside the batch: the Production keeps running on both machines.
	if (!batchDone) return;

	// Remove the matching Production (returns its engineers to the base pool) and
	// mirror the completion popup.
	for (auto* prod : base->getProductions())
	{
		if (prod->getRules()->getName() == mName)
		{
			if (payload.isMember("random")) // the host's list, so this window lists and sells what the host's does
			{
				std::map<std::string, int> info;
				for (const auto& k : payload["random"].getMemberNames()) info[k] = payload["random"][k].asInt();
				prod->setRandomProductionInfo(info);
			}
			GeoscapeState* gs = findGeoState(game);
			if (gs && SeparateEcon::showBaseNotification(game, base))
				game->pushState(new ProductionCompleteState(
					base, game->getLanguage()->getString(mName), gs,
					(productionProgress_e)payload.get("progress", PROGRESS_COMPLETE).asInt(),
					prod));
			base->removeProduction(prod);
			break;
		}
	}
}

// prod_fx payload: { manufacture, transfers: [yaml], crafts: [yaml], craftsRemoved: [{type, id}], stores?, engineers?, assigned?,
// ids: {counter: value}, score? }. host-origin after each Production::step that changed its
// base - the replica adopts the host's result (new transfers / crafts are the host's own YAML: soldier, craft, names, ids, owner);
// it never rolls. Funds ride the shared_apply. prod_done then only removes the production and shows the window.
void prodFxApply(Game* game, Json::Value& payload, Base* base, int /*seat*/)
{
	if (connectionTCP::getHost()) return; // the host's step wrote these
	if (!game || !base) return;
	SavedGame* save = game->getSavedGame();
	Mod* mod = game->getMod();
	if (!save || !mod) return;
	for (const auto& y : payload["transfers"])
	{
		YAML::YamlRootNodeReader reader(YAML::YamlString{ y.asString() }, "prod_fx transfer");
		auto* t = new Transfer(0);
		if (t->load(reader["n"], base, mod, save)) base->getTransfers()->push_back(t); // false: load already deleted it
	}
	for (const auto& y : payload["crafts"])
	{
		YAML::YamlRootNodeReader reader(YAML::YamlString{ y.asString() }, "prod_fx craft");
		const RuleCraft* cr = mod->getCraft(reader["n"]["type"].readVal<std::string>(), false);
		if (!cr) continue;
		auto* c = new Craft(cr, base);
		c->load(reader["n"], mod->getScriptGlobal(), mod, save);
		base->getCrafts()->push_back(c);
	}
	for (const auto& k : payload["craftsRemoved"])
		if (Craft* c = findCraft(base, k.get("id", -1).asInt(), k.get("type", "").asString())) { base->removeCraft(c, true); delete c; }
	if (payload.isMember("stores"))
	{
		base->getStorageItems()->clear();
		for (const auto& k : payload["stores"].getMemberNames())
			if (RuleItem* ri = mod->getItem(k, false)) base->getStorageItems()->addItem(ri, payload["stores"][k].asInt());
	}
	if (payload.isMember("engineers")) base->setEngineers(payload["engineers"].asInt());
	if (payload.isMember("assigned"))
		if (Production* p = findProduction(base, payload.get("manufacture", "").asString()))
			p->setAssignedEngineers(payload["assigned"].asInt());
	const std::map<std::string, int>& ids = save->getAllIds();
	for (const auto& k : payload["ids"].getMemberNames())
		while (ids.find(k) == ids.end() || ids.at(k) < payload["ids"][k].asInt()) save->getId(k);
	if (payload.isMember("score") && !save->getResearchScores().empty())
		save->getResearchScores().back() = payload["score"].asInt();
	Log(LOG_INFO) << "[SHARED] prod_fx: " << payload.get("manufacture", "").asString() << " at base " << baseIndex(game, base) << ": "
		<< payload["transfers"].size() << " transfer(s), " << payload["crafts"].size() << " craft(s)";
}

// transfer_arrived payload: { arrived: [ {type, rule, qty} ] }.
void transferArrivedApply(Game* game, Json::Value& payload, Base* base, int /*seat*/)
{
	if (connectionTCP::getHost()) return;
	if (!base) return;
	const Json::Value& arrived = payload["arrived"];
	if (!arrived.isArray()) return;

	auto& transfers = *base->getTransfers();
	for (const auto& d : arrived)
	{
		int type = d.get("type", -1).asInt();
		std::string rule = d.get("rule", "").asString();
		int qty = d.get("qty", 0).asInt();
		for (auto it = transfers.begin(); it != transfers.end(); ++it)
		{
			Transfer* t = *it;
			bool match = (t->getType() == type);
			if (match && type == TRANSFER_ITEM)
				match = (t->getItems() && t->getItems()->getType() == rule && t->getQuantity() == qty);
			else if (match && (type == TRANSFER_SCIENTIST || type == TRANSFER_ENGINEER))
				match = (t->getQuantity() == qty);
			else if (match && type == TRANSFER_CRAFT)
				match = (t->getCraft() && t->getCraft()->getRules()->getType() == rule);
			else if (match && type == TRANSFER_SOLDIER)
				// PRD-J05: hired/transferred soldiers arrive here too. Match by the
				// soldier's rule type (rule may be "" from an older host -> FIFO
				// falls back to the first pending soldier transfer, still correct
				// because host and replica built them in identical order).
				match = (t->getSoldier() && (rule.empty()
					|| t->getSoldier()->getRules()->getType() == rule));
			if (!match) continue;

			// Force delivery: advance() delivers exactly once when hours reach 0
			// and sets _delivered, so the subsequent delete won't free a craft/
			// soldier now owned by the base.
			while (t->getHours() > 0) t->advance(base);
			transfers.erase(it);
			delete t;
			break;
		}
	}
}

// the soldier_fx stats, named as the soldier_training_probe names them (UnitStats::fieldLoop order).
const std::pair<const char*, UnitStats::Ptr> kSoldierFxStats[] = {
	{"tu", &UnitStats::tu}, {"stamina", &UnitStats::stamina}, {"health", &UnitStats::health},
	{"bravery", &UnitStats::bravery}, {"reactions", &UnitStats::reactions}, {"firing", &UnitStats::firing},
	{"throwing", &UnitStats::throwing}, {"strength", &UnitStats::strength}, {"psiStrength", &UnitStats::psiStrength},
	{"psiSkill", &UnitStats::psiSkill}, {"melee", &UnitStats::melee}, {"mana", &UnitStats::mana}};

// one soldier's training / recovery record for soldier_fx (absolute values): the 12 current stats, this
// month's psi improvements, the three training flags, health / mana missing, the exact wound recovery and today's pilot experience.
Json::Value soldierFxRecord(Soldier* s)
{
	Json::Value r(Json::objectValue), st(Json::objectValue);
	for (const auto& f : kSoldierFxStats)
		st[f.first] = (int)(s->getCurrentStats()->*f.second);
	r["id"] = s->getId();
	r["stats"] = st;
	r["improvement"] = s->getImprovement();
	r["psiStrImprovement"] = s->getPsiStrImprovement();
	r["psiTraining"] = s->isInPsiTraining();
	r["training"] = s->isInTraining();
	r["rtwh"] = s->getReturnToTrainingWhenHealed();
	r["healthMissing"] = s->getHealthMissing();
	r["manaMissing"] = s->getManaMissing();
	r["recovery"] = (double)s->getWoundRecoveryExact(); // exact; replaces day_tick's cached ceil
	UnitStats* xp = s->getDailyDogfightExperienceCache(); // today's pilot experience
	r["dogfightXp"]["firing"] = (int)xp->firing; r["dogfightXp"]["reactions"] = (int)xp->reactions; r["dogfightXp"]["bravery"] = (int)xp->bravery;
	return r;
}

// day_tick payload: { productions:[{item,spent}],
// day_tick payload: { soldiers:[soldierStepJson], productions:[{item,spent}],
// research:[{project,spent}] }. PRD-J06: the replica's timeXxx handlers are
// frozen, so production _timeSpent and research _spent never advance locally;
// the host broadcasts the day's progress so the "days left" / "Progress" columns
// render current on replicas. Display-only (completion is host-driven J04).
// The soldier entries are the host's day/month step results (wounds, training);
// the replica adopts them exactly and never rolls its own.
void dayTickApply(Game* game, Json::Value& payload, Base* base, int /*seat*/)
{
	if (connectionTCP::getHost()) return;
	if (!base) return;
	const Json::Value& soldiers = payload["soldiers"];
	if (soldiers.isArray())
		for (const auto& s : soldiers)
		{
			Soldier* soldier = findSoldierAtBase(base, s.get("id", -1).asInt(),
				s.get("owner", -1).asInt());
			if (!soldier) continue;
			soldier->setWoundRecoveryExact((float)s.get("recovery", 0.0).asDouble());
			soldier->setHealthMissing(s.get("healthMissing", soldier->getHealthMissing()).asInt());
			soldier->setManaMissing(s.get("manaMissing", soldier->getManaMissing()).asInt());
			readUnitStats(s["stats"], *soldier->getCurrentStatsEditable());
			readUnitStats(s["dogfight"], *soldier->getDailyDogfightExperienceCache());
			soldier->setTraining(s.get("training", soldier->isInTraining()).asBool());
			soldier->setPsiTraining(s.get("psiTraining", soldier->isInPsiTraining()).asBool());
			soldier->setReturnToTrainingWhenHealed(
				s.get("trainingQueued", soldier->getReturnToTrainingWhenHealed()).asBool());
			soldier->setImprovements(s.get("improvement", soldier->getImprovement()).asInt(),
				s.get("psiStrImprovement", soldier->getPsiStrImprovement()).asInt());
			// The stat string is derived; recompute it the way loading a save does.
			SavedGame* save = game->getSavedGame();
			Mod* mod = game->getMod();
			soldier->calcStatString(mod->getStatStrings(),
				Options::psiStrengthEval && save->isResearched(mod->getPsiRequirements()));
		}
	const Json::Value& productions = payload["productions"];
	if (productions.isArray())
		for (const auto& pr : productions)
		{
			Production* p = findProduction(base, pr.get("item", "").asString());
			if (p) p->setTimeSpent(pr.get("spent", p->getTimeSpent()).asInt());
		}
	const Json::Value& research = payload["research"];
	if (research.isArray())
		for (const auto& rr : research)
		{
			ResearchProject* rp = findResearchProject(base, rr.get("project", "").asString());
			if (rp) rp->setSpent(rr.get("spent", rp->getSpent()).asInt());
		}
}

// soldier_fx payload: { soldiers: [soldierFxRecord] }. host-origin after the host's day / month
// soldier loops - the replica adopts the host's training and recovery results (it never rolls its own: time1Day is
// frozen and time1MonthCoop's psi block is gated on a SHARED replica). Replica only; no RNG, no training call.
void soldierFxApply(Game* game, Json::Value& payload, Base* base, int /*seat*/)
{
	if (connectionTCP::getHost()) return; // the host's own loops wrote these values
	if (!game || !base) return;
	const Json::Value& soldiers = payload["soldiers"];
	if (!soldiers.isArray()) return;
	Mod* mod = game->getMod();
	SavedGame* save = game->getSavedGame();
	// the stat string with THIS player's display option (psiStrengthEval is not a synced option)
	const bool psiStrengthEval = Options::psiStrengthEval && save && save->isResearched(mod->getPsiRequirements());
	int adopted = 0;
	for (const auto& r : soldiers)
	{
		Soldier* s = findSoldier(base, r.get("id", -1).asInt());
		if (!s) continue; // not at this base here: left out of the adopted count
		UnitStats* u = s->getCurrentStatsEditable();
		for (const auto& f : kSoldierFxStats)
			u->*f.second = (UnitStats::Type)r["stats"].get(f.first, (int)(u->*f.second)).asInt();
		s->setImprovements(r.get("improvement", s->getImprovement()).asInt(),
			r.get("psiStrImprovement", s->getPsiStrImprovement()).asInt());
		s->setPsiTraining(r.get("psiTraining", s->isInPsiTraining()).asBool());
		s->setTraining(r.get("training", s->isInTraining()).asBool());
		s->setReturnToTrainingWhenHealed(r.get("rtwh", s->getReturnToTrainingWhenHealed()).asBool());
		s->setHealthMissing(r.get("healthMissing", s->getHealthMissing()).asInt());
		s->setManaMissing(r.get("manaMissing", s->getManaMissing()).asInt());
		s->setWoundRecoveryExact((float)r.get("recovery", (double)s->getWoundRecoveryExact()).asDouble());
		UnitStats* xp = s->getDailyDogfightExperienceCache();
		const Json::Value& jx = r["dogfightXp"];
		xp->firing = (UnitStats::Type)jx.get("firing", (int)xp->firing).asInt();
		xp->reactions = (UnitStats::Type)jx.get("reactions", (int)xp->reactions).asInt();
		xp->bravery = (UnitStats::Type)jx.get("bravery", (int)xp->bravery).asInt();
		s->calcStatString(mod->getStatStrings(), psiStrengthEval);
		++adopted;
	}
	Log(LOG_INFO) << "[SHARED] soldier_fx: " << adopted << " of " << soldiers.size() << " soldier(s) at base "
		<< baseIndex(game, base);
}

// craft_lost payload: { craftId, craftType, evacuated: [{id, hours, training, rtwh}], killed: [id] } (baseId = the craft's base).
// host-origin when the host's time5Seconds removes a destroyed craft. The replica queues it and
// flushLostCrafts applies vanilla's sequence from the replica's own geoscape think, never while one of its dogfight windows still
// holds the craft. No RNG: the host resolved who escaped.
std::vector<std::pair<int, Json::Value> > g_lostCrafts; // replica: (base index, payload) waiting for the geoscape

void craftLostApply(Game* game, Json::Value& payload, Base* base, int /*seat*/)
{
	if (connectionTCP::getHost()) return; // the host's vanilla block already did it
	if (!game || !base) return;
	g_lostCrafts.push_back(std::make_pair(baseIndex(game, base), payload));
}

// unassign_wounded payload: { ids: [soldier id] } (baseId = the debriefing base).
// Host-origin at a SHARED campaign debriefing's OK - mirrors vanilla's host-only wounded loop (replicas only).
void unassignWoundedApply(Game* game, Json::Value& payload, Base* base, int /*seat*/)
{
	if (connectionTCP::getHost()) return; // the host's vanilla loop already did it
	if (!game || !base) return;
	const Json::Value& ids = payload["ids"];
	if (!ids.isArray()) return;
	int unassigned = 0;
	for (const auto& v : ids)
		for (auto* soldier : *base->getSoldiers())
			if (soldier->getId() == v.asInt() && soldier->getCraft() != nullptr)
			{
				soldier->setCraftAndMoveEquipment(nullptr, base, false);
				++unassigned;
				break;
			}
	Log(LOG_INFO) << "[SHARED] unassign_wounded: " << unassigned << " of " << ids.size() << " soldier(s) off their crafts";
}

// ---- the sel_* commands and the host's confirm rules ----
// Key "<screen>|<variant>|<baseIdx>|<extra>" (sellKey / xferKey / contKey).
bool selParseKey(const std::string& key, std::string& screen, char& variant, int& baseIdx, std::string& extra)
{
	const size_t a = key.find('|'), b = a == std::string::npos ? a : key.find('|', a + 1);
	const size_t c = b == std::string::npos ? b : key.find('|', b + 1);
	if (c == std::string::npos || b != a + 2 || c == b + 1) return false;
	screen = key.substr(0, a); variant = key[a + 1]; extra = key.substr(c + 1);
	try { baseIdx = std::stoi(key.substr(b + 1, c - b - 1)); } catch (...) { return false; }
	return screen == "sell" || screen == "xfer" || screen == "cont" || screen == "buy"; // + buy
}

// What the host's confirm validator would accept for @a row now. Sell (sellValidate's rules): i: =
// base stock (forced: what the forced screen lists); s: 1 iff that soldier is at the base off its craft; c: 1 iff
// the craft is there and not out; sci / eng <= available. Unknown or negative -> 0 (erased). Transfer the same
// (transferValidate's, from the source; c: 1 iff the craft is there), containment i: = stock only (containmentValidate's).
int selClamp(Game* game, const std::string& key, const std::string& row, int amount)
{
	std::string screen, extra; char variant = 'n'; int idx = -1;
	if (amount <= 0 || !selParseKey(key, screen, variant, idx, extra)) return 0;
	Base* base = resolveBase(game, idx);
	if (!base || (screen == "cont" && row.compare(0, 2, "i:") != 0)) return 0;
	if (screen == "buy") // per row only - an unknown rule -> 0, else the mods-only
	{                    // monthly limit; funds / stores / quarters / hangars / containment stay buyValidate's
		if (row == "sci" || row == "eng") return amount;
		Mod* mod = game->getMod();
		const bool item = row.compare(0, 2, "i:") == 0, hire = row.compare(0, 2, "h:") == 0, craft = row.compare(0, 3, "cr:") == 0;
		const std::string type = item || hire ? row.substr(2) : craft ? row.substr(3) : std::string();
		const RuleItem* ri = item ? mod->getItem(type, false) : nullptr;
		const RuleSoldier* rs = hire ? mod->getSoldier(type, false) : nullptr;
		const RuleCraft* rc = craft ? mod->getCraft(type, false) : nullptr;
		if (!ri && !rs && !rc) return 0;
		const int limit = ri ? ri->getMonthlyBuyLimit() : rs ? rs->getMonthlyBuyLimit() : rc->getMonthlyBuyLimit();
		if (limit <= 0) return amount;
		const auto& log = game->getSavedGame()->getMonthlyPurchaseLimitLog();
		const auto used = log.find(type);
		return std::max(0, std::min(amount, limit - (used == log.end() ? 0 : used->second)));
	}
	if (row.compare(0, 2, "i:") == 0)
	{
		const RuleItem* rule = game->getMod()->getItem(row.substr(2), false);
		return !rule ? 0 : std::min(amount, screen == "sell" && variant == 'f'
			? forcedSellAvailable(base, rule, base->storesOverfullCritical()) : base->getStorageItems()->getItem(rule));
	}
	for (auto* s : *base->getSoldiers())
		if (row == "s:" + std::to_string(s->getId())) return s->getCraft() == 0 ? 1 : 0;
	for (auto* c : *base->getCrafts())
		if (row == "c:" + std::to_string(c->getId()) + ":" + c->getRules()->getType())
			return screen == "xfer" || c->getStatus() != "STR_OUT" ? 1 : 0;
	if (row == "sci" || row == "eng") return std::min(amount, row == "sci" ? base->getAvailableScientists() : base->getAvailableEngineers());
	return 0;
}

// FNV-1a 64 over the sorted "row=amount;" pairs: the identity of a consumed selection.
uint64_t selHash(const std::map<std::string, int>& rows)
{
	uint64_t h = 1469598103934665603ULL;
	for (const auto& r : rows)
		for (char ch : r.first + "=" + std::to_string(r.second) + ";") h = (h ^ (unsigned char)ch) * 1099511628211ULL;
	return h;
}

std::map<std::string, int> selMapOf(const Json::Value& v, bool positiveOnly)
{
	std::map<std::string, int> m;
	for (const auto& k : v.isObject() ? v.getMemberNames() : Json::Value::Members())
		if (!positiveOnly || v[k].asInt() > 0) m[k] = v[k].asInt();
	return m;
}

// The list's full state, as every sel_* broadcast carries it (the host resolves it; a replica adopts it verbatim).
Json::Value selStateJson(const std::string& key)
{
	Json::Value st(Json::objectValue);
	auto it = g_sel.find(key);
	st["erased"] = it == g_sel.end();
	if (it == g_sel.end()) return st;
	const char* names[] = { "rows", "editors", "eseqs" };
	const std::map<std::string, int>* maps[] = { &it->second.rows, &it->second.editors, &it->second.eseqs };
	for (int i = 0; i < 3; ++i)
	{
		st[names[i]] = Json::Value(Json::objectValue);
		for (const auto& kv : *maps[i]) st[names[i]][kv.first] = kv.second;
	}
	st["rev"] = Json::UInt(it->second.rev);
	st["viewers"] = Json::Value(Json::arrayValue);
	for (int seat : it->second.viewers) st["viewers"].append(seat); // std::set: sorted
	return st;
}

// sel_open {key, seed} / sel_set {key, row, amount, eseq} / sel_close {key} / sel_sync {key} (host-origin).
// The host applies the rule and resolves the list's full state into payload["state"]; a replica adopts it. Then this
// machine notes its own open answered and its own edits seen. A malformed payload changes nothing (never a
// reject: a reject would raise a fail box).
void selApplyOp(Game* game, Json::Value& payload, int seat, const std::string& op)
{
	const std::string key = payload.get("key", "").asString(), row = payload.get("row", "").asString();
	std::string screen, extra; char variant = 'n'; int idx = -1;
	if (!selParseKey(key, screen, variant, idx, extra) || (op == "sel_set" && row.empty()))
		{ Log(LOG_WARNING) << "[SHARED] sel: malformed " << op << " (key '" << key << "') ignored"; return; }
	if (isHost())
	{
		auto it = g_sel.find(key);
		if (op == "sel_open")
		{
			SharedSel& s = g_sel[key];
			s.viewers.erase(seat);
			if (s.viewers.empty()) // a lone opener starts the list: at zero, or with its seed
			{
				s.rows.clear(); s.editors.clear(); s.eseqs.clear();
				for (const auto& r : selMapOf(payload.get("seed", Json::Value()), true))
					if (const int a = selClamp(game, key, r.first, r.second)) { s.rows[r.first] = a; s.editors[r.first] = seat; }
				++s.rev;
			}
			s.viewers.insert(seat);
		}
		else if (it == g_sel.end())
			Log(LOG_INFO) << "[SHARED] sel: " << op << " for " << key << ", which nobody has open - no change";
		else if (op == "sel_set")
		{
			const int a = selClamp(game, key, row, payload.get("amount", 0).asInt());
			if (a > 0) it->second.rows[row] = a; else it->second.rows.erase(row);
			it->second.editors[row] = seat; // kept at amount 0 until the list clears: the sender always sees its echo
			it->second.eseqs[row] = payload.get("eseq", 0).asInt();
			++it->second.rev;
		}
		else if (op == "sel_close")
			{ it->second.viewers.erase(seat); if (it->second.viewers.empty()) g_sel.erase(it); }
		else // sel_sync: re-clamp to the world as it is now
		{
			std::map<std::string, int> rows;
			for (const auto& r : it->second.rows)
				if (const int a = selClamp(game, key, r.first, r.second)) rows[r.first] = a;
			if (rows != it->second.rows) { it->second.rows = rows; ++it->second.rev; }
		}
		payload["state"] = selStateJson(key);
	}
	else
	{
		const Json::Value st = payload.get("state", Json::Value());
		if (!st.isObject()) { Log(LOG_WARNING) << "[SHARED] sel: " << op << " for " << key << " without a state ignored"; return; }
		if (st.get("erased", false).asBool()) g_sel.erase(key);
		else
		{
			SharedSel& s = g_sel[key];
			s.rows = selMapOf(st["rows"], true); s.editors = selMapOf(st["editors"], false);
			s.eseqs = selMapOf(st["eseqs"], false); s.rev = st.get("rev", 0).asUInt(); s.viewers.clear();
			for (const auto& v : st["viewers"]) s.viewers.insert(v.asInt());
		}
	}
	SelLocal& loc = g_selLocal[key];
	const int me = connectionTCP::localSeat();
	if (op == "sel_open" && seat == me) ++loc.openEchoes;
	auto it = g_sel.find(key);
	if (it != g_sel.end())
		for (const auto& e : it->second.editors)
			if (e.second == me && it->second.eseqs.count(e.first))
				loc.ownSeen[e.first] = std::max(loc.ownSeen[e.first], it->second.eseqs.at(e.first));
}

// A stamped confirm applied on a list - host: remember what was consumed, clear the list, rev++ and
// stamp the new rev; replica: clear the mirror and adopt that rev. Every binder then shows zeros.
void selConsume(Json::Value& payload)
{
	const std::string key = payload.get("selKey", "").asString();
	auto it = g_sel.find(key);
	if (it == g_sel.end() || (isHost() ? g_selConfirmKey != key : !payload.isMember("selRevAfter"))) return;
	SharedSel& s = it->second;
	if (isHost()) { s.consumed = true; s.consumedRev = s.rev; s.consumedHash = g_selConfirmHash; g_selConfirmKey.clear(); }
	s.rows.clear(); s.editors.clear(); s.eseqs.clear();
	if (isHost()) payload["selRevAfter"] = Json::UInt(++s.rev);
	else s.rev = payload["selRevAfter"].asUInt();
	Log(LOG_INFO) << "[SHARED] sel: " << key << " consumed (rev " << s.rev << ")";
}

// Before the validate of a confirm stamped with a list the host holds: (i) the duplicate
// of a consumed selection -> true = coop_sel_dup, a success; (ii) the row arrays are rebuilt from the host's clamped
// list (the host applies its current list, whatever rev the confirm saw; page 3 also capped by the stamped selCaps),
// every other key stays the confirmer's; (iii) nothing left on a non-page-3 key -> true; (iv) a key the host does
// not hold -> false, applied as sent. "sell", "transfer" (+ the soldiers' gear), "containment" and "buy" alike.
bool selConfirmRules(Game* game, const PendingCmd& pc, Json::Value& cmdPayload)
{
	g_selConfirmKey.clear();
	const std::string key = cmdPayload.get("selKey", "").asString();
	const std::string screen = pc.cmd == "sell" ? "sell|" : pc.cmd == "transfer" ? "xfer|" : pc.cmd == "containment" ? "cont|"
		: pc.cmd == "buy" ? "buy|" : ""; // + buy
	auto it = !screen.empty() && key.compare(0, screen.size(), screen) == 0 ? g_sel.find(key) : g_sel.end();
	if (it == g_sel.end()) return false;
	const SharedSel& s = it->second;
	if (s.consumed && cmdPayload.get("selRev", 0).asUInt() <= s.consumedRev
		&& selHash(selMapOf(cmdPayload.get("selRows", Json::Value()), true)) == s.consumedHash) return true;
	const bool page3 = key.find("|d|") != std::string::npos;
	const Json::Value caps = cmdPayload.get("selCaps", Json::Value());
	std::map<std::string, int> rows;
	for (const auto& r : s.rows)
	{
		int a = selClamp(game, key, r.first, r.second);
		if (page3 && r.first.compare(0, 2, "i:") == 0) a = std::min(a, caps.get(r.first, 0).asInt());
		if (a > 0) rows[r.first] = a;
	}
	if (rows.empty() && !page3) return true;
	if (pc.cmd == "buy") // typed rows (Transfer.h: ITEM 0, CRAFT 1, SOLDIER 2, SCIENTIST 3, ENGINEER 4)
	{                    // from the host's list; total (an estimate the validator ignores) and reequip stay the confirmer's
		Json::Value buy(Json::arrayValue);
		for (const auto& r : rows)
		{
			Json::Value e;
			const bool staff = r.first == "sci" || r.first == "eng";
			e["type"] = (int)(r.first == "sci" ? TRANSFER_SCIENTIST : r.first == "eng" ? TRANSFER_ENGINEER : r.first.compare(0, 2, "i:") == 0
				? TRANSFER_ITEM : r.first.compare(0, 3, "cr:") == 0 ? TRANSFER_CRAFT : TRANSFER_SOLDIER);
			e["rule"] = staff ? std::string() : r.first.substr(r.first.find(':') + 1);
			e["qty"] = r.second;
			if (r.first.compare(0, 2, "h:") == 0 && s.editors.count(r.first)) e["owner"] = s.editors.at(r.first); // the row's last editor owns its hires
			buy.append(e);
		}
		cmdPayload["items"] = buy;
		g_selConfirmKey = key; g_selConfirmHash = selHash(rows);
		return false;
	}
	Json::Value items(Json::arrayValue), soldiers(Json::arrayValue), crafts(Json::arrayValue);
	for (const auto& r : rows)
	{
		const size_t p = r.first.find(':', 2);
		Json::Value e;
		if (r.first.compare(0, 2, "i:") == 0) { e["rule"] = r.first.substr(2); e["qty"] = r.second; items.append(e); }
		else if (r.first.compare(0, 2, "s:") == 0) soldiers.append(std::atoi(r.first.c_str() + 2));
		else if (r.first.compare(0, 2, "c:") == 0 && p != std::string::npos)
			{ e["id"] = std::atoi(r.first.substr(2, p - 2).c_str()); e["type"] = r.first.substr(p + 1); crafts.append(e); }
	}
	// The soldiers' alternate-equipment gear as item rows, TransferItemsState :784-:817's rule on this world.
	Base* from = pc.cmd == "transfer" ? resolveBase(game, pc.baseId) : nullptr;
	if (from && Options::oxceAlternateCraftEquipmentManagement && !soldiers.empty())
	{
		std::map<const RuleItem*, int> claimed, gear;
		for (const auto& e : items) claimed[game->getMod()->getItem(e["rule"].asString(), false)] += e["qty"].asInt();
		auto take = [&](const RuleItem* rule)
			{ if (rule && claimed[rule] + gear[rule] < from->getStorageItems()->getItem(rule)) gear[rule]++; };
		for (auto* sol : *from->getSoldiers())
			if (rows.count("s:" + std::to_string(sol->getId())))
				for (auto* li : *sol->getEquipmentLayout())
				{
					take(li->getItemType());
					for (int slot = 0; slot < RuleItem::AmmoSlotMax; ++slot) take(li->getAmmoItemForSlot(slot));
				}
		for (const auto& g : gear) { Json::Value e; e["rule"] = g.first->getType(); e["qty"] = g.second; items.append(e); }
	}
	if (pc.cmd == "containment") cmdPayload["prisoners"] = items; // a containment list holds i: rows only
	else
	{
		cmdPayload["items"] = items; cmdPayload["soldiers"] = soldiers; cmdPayload["crafts"] = crafts;
		cmdPayload["scientists"] = rows.count("sci") ? rows["sci"] : 0;
		cmdPayload["engineers"] = rows.count("eng") ? rows["eng"] : 0;
	}
	g_selConfirmKey = key; g_selConfirmHash = selHash(rows);
	return false;
}

void processHostCmd(Game* game, const PendingCmd& pc);

// After a world apply the host re-clamps every list it touched (its base; a transfer's destination and
// every xfer key naming either; baseId < 0 = every list) and sel_syncs each changed one AT ONCE, never through g_cmdQ:
// the apply's broadcast precedes the sel_sync's on the ordered lane, so no queued confirm sees an unclamped list.
void selSyncTouched(Game* game, const PendingCmd& pc)
{
	const int toBase = pc.cmd == "transfer" ? pc.payload.get("toBaseId", -1).asInt() : -1;
	std::vector<std::pair<std::string, int>> changed;
	for (const auto& kv : g_sel)
	{
		std::string screen, extra; char variant = 'n'; int idx = -1;
		if (!selParseKey(kv.first, screen, variant, idx, extra)) continue;
		const std::string other = screen == "xfer" ? extra : "";
		const bool touched = pc.baseId < 0 || idx == pc.baseId || (toBase >= 0 && idx == toBase)
			|| (!other.empty() && (other == std::to_string(pc.baseId) || (toBase >= 0 && other == std::to_string(toBase))));
		for (const auto& r : kv.second.rows)
			if (touched && selClamp(game, kv.first, r.first, r.second) != r.second) { changed.push_back({ kv.first, idx }); break; }
	}
	for (const auto& c : changed)
	{
		PendingCmd sync;
		sync.cmd = "sel_sync"; sync.seq = ++g_seqCounter; sync.seat = connectionTCP::localSeat();
		sync.baseId = c.second; sync.payload["key"] = c.first;
		processHostCmd(game, sync);
	}
}

// ---- Host-side command processing (main thread) ------------------------------
void rejectHostCmd(Game* game, const PendingCmd& pc, const std::string& reason)
{
	++g_failN;
	setLastFail(reason);
	if (pc.remote)
	{
		Json::Value fail;
		fail["state"] = pc.separateProtocol ? "separate_fail" : "shared_fail";
		fail["seq"] = pc.seq;
		fail["reason"] = reason;
		if (game->getCoopMod()) game->getCoopMod()->sendTCPPacketData(fail.toStyledString());
	}
	else
	{
		// The host's own command failed: surface it locally, exactly as a replica
		// surfaces a shared_fail received from the host (PRD-J10: one helper, one
		// dialog, both roles).
		showFail(game, reason);
		recordResult(pc.seq, reason == "coop_sel_dup" ? 1 : -1); // the host's own awaiting screen stays under the box; a duplicate confirm is a success
	}
}

void processHostCmd(Game* game, const PendingCmd& pc)
{
	auto& reg = registry();
	auto hit = reg.find(pc.cmd);
	if (hit == reg.end())
	{
		++g_unknownN;
		rejectHostCmd(game, pc, "unknown command: " + pc.cmd);
		return;
	}

	// A screen's sel_close may be queued in the teardown frame before the world is dropped.
	if (!game->getSavedGame() && pc.cmd.compare(0, 4, "sel_") == 0) { Log(LOG_WARNING) << "[SHARED] " << pc.cmd << " dropped: no world"; return; }
	// The sender named its bases by index in ITS list and by key; this machine's
	// index for the same base is what replicas and appliers use from here on.
	Base* base = resolveBaseRef(game, pc.baseId, pc.baseKey);
	const int hostBaseId = base ? baseIndex(game, base) : (pc.baseKey ? -1 : pc.baseId);
	Json::Value cmdPayload = pc.payload;
	resolvePayloadBaseRefs(game, cmdPayload);
	// Schema-3 SEPARATE policy is intentionally stricter than SHARED.  A seat may
	// mutate only bases carrying its player name. The explicit player-facing
	// foreign-base exceptions are the agreed co-op services: purchasing into that
	// base and equipping/rearming a craft stationed there. Host simulation results
	// are not player actions: they must reach every replica even when the affected
	// base belongs to another player (most visibly transfer_arrived, which removes
	// an arrived soldier from the replica's Transfers list). Keep the distinction
	// host-side so a stale or modified client UI can never bypass ownership.
	if (pc.separateProtocol && base && game && game->getSavedGame()
		&& game->getSavedGame()->isSeparateCoopCampaign())
	{
		const std::string playerName = connectionTCP::seatName(pc.seat);
		const bool foreign = !base->isOwnedByPlayer(playerName);
		const bool foreignAllowed = SeparateEcon::allowsForeignBaseCommand(
			pc.cmd, pc.remote, cmdPayload, base, pc.seat);
		if (foreign && !foreignAllowed)
		{
			// Normal Separate UI permissions prevent most of these actions; the
			// host keeps the security boundary. Tell the player who asked (the
			// remote initiator gets separate_fail, the host's own command shows
			// the fail dialog locally) instead of dropping it silently. The host
			// diagnostic keeps its own text for the harness. A host simulation
			// result (simAccept validator) is not a player action: no dialog.
			using SimValidator = bool (*)(Game*, const Json::Value&, Base*, int,
				int64_t&, std::string&);
			const SimValidator* fn = hit->second.validate.target<SimValidator>();
			if (fn && *fn == &simAccept)
				++g_failN;
			else
				rejectHostCmd(game, pc, "STR_COOP_ACTION_REFUSED");
			setLastFail("foreign base command rejected");
			return;
		}
	}
	SavedGame* save = game->getSavedGame();
	// A host simulation result (prod_done, research_done, ...) settles the base
	// owner's wallet, so it reports that wallet to replicas, not the host seat's.
	const std::string fundsPlayer = !pc.separateProtocol ? std::string()
		: (!pc.remote && base && !base->getOwnerPlayerName().empty()
			&& SeparateEcon::isHostSimulationResult(pc.cmd))
			? base->getOwnerPlayerName() : connectionTCP::seatName(pc.seat);
	if (pc.separateProtocol && save)
		save->setSeparateFundsContext(fundsPlayer);
	int64_t cost = 0;
	std::string failReason;
	++g_cmdN;
	// a stamped confirm is checked and rewritten from the host's list before the validate.
	if (selConfirmRules(game, pc, cmdPayload)) // a success
	{
		if (pc.separateProtocol && save) save->clearSeparateFundsContext();
		rejectHostCmd(game, pc, "coop_sel_dup");
		return;
	}
	if (!hit->second.validate(game, cmdPayload, base, pc.seat, cost, failReason))
	{
		if (pc.separateProtocol && save) save->clearSeparateFundsContext();
		rejectHostCmd(game, pc, failReason.empty() ? "rejected" : failReason);
		return;
	}

	// Passed: debit the authoritative funds, apply the mutation, then broadcast
	// shared_apply (carrying the post-mutation funds) to every peer and shared_ok
	// to the initiator. The applier gets a MUTABLE payload copy so it can resolve
	// host-only RNG into it (e.g. buy serializes generated soldiers); the resolved
	// payload is what we broadcast, so replicas reconstruct instead of re-rolling.
	// Replicas hold the host's base order up to this command, so the broadcast
	// names the base by the host's index from before the apply (and its key).
	const int baseKey = base ? base->_coop_base_id : 0;
	save->setFunds(save->getFunds() - cost);
	Json::Value payload = cmdPayload;
	hit->second.apply(game, payload, base, pc.seat);
	++g_applyN;

	Json::Value apply;
	apply["state"] = pc.separateProtocol ? "separate_apply" : "shared_apply";
	apply["cmd"] = pc.cmd;
	apply["seq"] = pc.seq;
	apply["seat"] = pc.seat;
	apply["baseId"] = hostBaseId;
	apply["baseKey"] = baseKey;
	apply["payload"] = payload;
	apply["funds"] = Json::Value::Int64(save->getFunds());
	if (pc.separateProtocol) apply["fundsPlayer"] = fundsPlayer;
	// GAP-9: carry the host's authoritative current-month income/expenditure tails
	// (read AFTER apply, so they include any gross flow the applier booked, e.g. a
	// prod_done that both sells and restarts a unit). The replica adopts these
	// verbatim instead of net-inferring them from setFunds, keeping the Graphs->
	// Finance series exactly the host's. Funds alone are not enough: the host's
	// gross income/expenditure decomposition cannot be reconstructed from the net.
	if (!save->getIncomes().empty())
		apply["incTail"] = Json::Value::Int64(save->getIncomes().back());
	if (!save->getExpenditures().empty())
		apply["expTail"] = Json::Value::Int64(save->getExpenditures().back());
	broadcast(game, apply);

	if (pc.remote && game->getCoopMod())
	{
		Json::Value ok;
		ok["state"] = pc.separateProtocol ? "separate_ok" : "shared_ok";
		ok["seq"] = pc.seq;
		game->getCoopMod()->sendTCPPacketData(ok.toStyledString());
		++g_okN;
	}

	// PRD-J10: the host's own open screens are as stale as a replica's after an
	// apply (a client's buy moves the host's funds too), so both roles notify.
	fireApplyListener(pc.cmd, hostBaseId, pc.seat);
	if (!pc.remote) recordResult(pc.seq, 1); // the host's own awaiting screen closes
	if (pc.cmd.compare(0, 4, "sel_") != 0) selSyncTouched(game, pc); // re-clamp the touched lists now
	if (pc.separateProtocol && save) save->clearSeparateFundsContext();
}

// ---- Replica-side apply (main thread) ----------------------------------------
void processApply(Game* game, const Json::Value& ap)
{
	SavedGame* save = game->getSavedGame();
	const bool separateApply = ap.get("state", "").asString() == "separate_apply";
	if (save && separateApply)
	{
		std::string fundsPlayer = ap.get("fundsPlayer", "").asString();
		if (fundsPlayer.empty())
			fundsPlayer = connectionTCP::seatName(ap.get("seat", 0).asInt());
		save->setSeparateFundsContext(fundsPlayer);
	}
	// Funds are host-authoritative: adopt them from the packet no matter what, so
	// the replica cannot drift even if the mutation itself cannot be reconstructed.
	if (save && ap.isMember("funds"))
	{
		if (ap.isMember("incTail") && ap.isMember("expTail"))
		{
			// GAP-9: adopt the host's authoritative funds AND its income/expenditure
			// tails verbatim. setFunds() would net-infer the direction from the delta
			// and drift the Graphs->Finance series (the host reached this value through
			// gross income AND expenditure, e.g. a prod_done that sells + restarts a
			// unit); setFundsRaw() moves only _funds.back(), then we copy the tails.
			save->setFundsRaw(ap["funds"].asInt64());
			if (!save->getIncomes().empty())
				save->getIncomes().back() = ap["incTail"].asInt64();
			if (!save->getExpenditures().empty())
				save->getExpenditures().back() = ap["expTail"].asInt64();
		}
		else
		{
			// Legacy packet without the series tails: keep the old net-inference so
			// funds still stay exact (series may drift, as before the fix).
			save->setFunds(ap["funds"].asInt64());
		}
	}

	std::string cmd = ap.get("cmd", "").asString();
	Base* base = resolveBaseRef(game, ap.get("baseId", -1).asInt(), ap.get("baseKey", 0).asInt());
	const int applyBaseId = base ? baseIndex(game, base) : ap.get("baseId", -1).asInt();
	auto& reg = registry();
	auto hit = reg.find(cmd);
	// NOTE: no "!base" early-return here. A creation command (base_new) carries
	// baseId=-1 (no existing base) and its applier ignores @a base; every OTHER
	// applier already null-guards @a base itself (if (!base) return;), so passing a
	// null base straight through is safe and keeps base creation working on replicas.
	if (hit == reg.end())
	{
		if (save && separateApply) save->clearSeparateFundsContext();
		return;
	}

	// Mutable copy for the applier signature; the replica only READS the resolved
	// payload (host already resolved any RNG before broadcasting).
	Json::Value payload = ap["payload"];
	resolvePayloadBaseRefs(game, payload);
	int seat = ap.get("seat", 0).asInt();
	hit->second.apply(game, payload, base, seat);
	if (save && separateApply) save->clearSeparateFundsContext();
	++g_applyN;

	// PRD-J10: tell the open screen its world just moved under it.
	fireApplyListener(cmd, applyBaseId, seat);
}

} // anonymous namespace

// ---- Public API --------------------------------------------------------------

// coop: the SHARED pre-battle equip end's soldier
// gear records (both called from connectionTCP.cpp). soldierEquipRecord / soldierEquipAdopt sit in the anonymous namespace above;
// these two are their public seam. HOST: one record per battle unit with a geoscape soldier - id, layout, personal, personalArmor
// (no name).
Json::Value equipEndGearRecords(SavedBattleGame* save)
{
	Json::Value out(Json::arrayValue);
	if (!save)
		return out;
	for (BattleUnit* bu : *save->getUnits())
	{
		Soldier* s = bu ? bu->getGeoscapeSoldier() : nullptr;
		if (!s)
			continue;
		Json::Value r = soldierEquipRecord(s);
		r.removeMember("name"); // the gear only
		out.append(r);
	}
	return out;
}

// coop: CLIENT - each record into the soldier of this machine's battle unit with that soldier id (soldierEquipAdopt: the
// present fields only). Returns the records adopted; a record with no such unit is skipped.
int equipEndGearAdopt(Game* game, SavedBattleGame* save, const Json::Value& records)
{
	int adopted = 0;
	if (!game || !save || !records.isArray())
		return adopted;
	for (const auto& r : records)
	{
		const int id = r.get("id", -1).asInt();
		for (BattleUnit* bu : *save->getUnits())
		{
			Soldier* s = bu ? bu->getGeoscapeSoldier() : nullptr;
			if (s && s->getId() == id)
			{
				soldierEquipAdopt(game, s, r);
				++adopted;
				break;
			}
		}
	}
	return adopted;
}

void registerCmd(const std::string& cmd, CmdValidator validate, CmdApplier apply)
{
	registry()[cmd] = Handler{ std::move(validate), std::move(apply) };
}

// ---- PRD-J10: apply notification ---------------------------------------------
void setApplyListener(const void* owner, ApplyListener listener)
{
	g_listenerOwner = owner;
	g_listener = std::move(listener);
}

void clearApplyListener(const void* owner)
{
	// Only the CURRENT owner may clear. A popped screen's destructor runs one
	// frame late - by then its replacement already registered, and an
	// unconditional clear here would kill live refresh for good.
	if (g_listenerOwner != owner) return;
	g_listenerOwner = nullptr;
	g_listener = nullptr;
}

int lastApplySeat()
{
	return g_lastApplySeat.load();
}

int baseIndex(Game* game, const Base* base)
{
	if (!game || !game->getSavedGame() || !base) return -1;
	auto* bases = game->getSavedGame()->getBases();
	for (size_t i = 0; i < bases->size(); ++i)
		if ((*bases)[i] == base) return (int)i;
	return -1;
}

Base* resolveBaseReference(Game* game, int baseId, int baseKey)
{
	return resolveBaseRef(game, baseId, baseKey);
}

int baseMoveTarget(Game* game, const Base* base)
{
	const int from = baseIndex(game, base);
	if (from <= 0) return -1;
	SavedGame* save = game->getSavedGame();
	if (!save->isSeparateCoopCampaign()) return from - 1;
	// The Separate strip lists each player's own bases together, so a base moves
	// past the previous base of the same owner.
	auto* bases = save->getBases();
	for (int i = from - 1; i >= 0; --i)
		if ((*bases)[i]->getOwnerPlayerName() == base->getOwnerPlayerName()) return i;
	return -1;
}

void ScreenRefresh::bind(Game* game, const void* owner, Base* base, bool wantProgress)
{
	if (!game || !game->getCoopMod() || !(game->getCoopMod()->isSharedCampaign() || game->getCoopMod()->isSeparateCampaign())) return;
	_game = game;
	_base = base;
	_wantProgress = wantProgress;
	_bound = true;
	setApplyListener(owner, [this](const std::string& cmd, int applyBaseId)
	{
		// day_tick is pure progress bookkeeping (wound recovery, research/production
		// "days left"). List views want it; a command screen must NOT throw away the
		// player's half-entered order once per game-day because of it.
		if (cmd.compare(0, 4, "sel_") == 0) return; // selection traffic never rebuilds a screen
		if (!_wantProgress && cmd == "day_tick") return;
		if (!_wantProgress && cmd == "soldier_fx") return; // per-day soldier bookkeeping, like day_tick
		// applyBaseId < 0 = world-scoped (funds-only, base creation, dogfights):
		// always relevant. Otherwise only this screen's own base matters.
		if (applyBaseId >= 0 && _base)
		{
			int mine = baseIndex(_game, _base);
			if (mine >= 0 && mine != applyBaseId) return;
		}
		_dirty = true;
	});
}

void ScreenRefresh::unbind(const void* owner)
{
	clearApplyListener(owner);
	_bound = false;
}

bool ScreenRefresh::consume()
{
	if (!_dirty) return false;
	_dirty = false;
	return true;
}

void showFail(Game* game, const std::string& reason)
{
	if (!game) return;
	if (reason == "coop_forced_resolved") return; // no box - the forced screen closes itself
	if (reason == "coop_sel_dup") return; // a duplicate confirm is a success - no box
	// The reason is the host validator's own string: an STR_ id where the vanilla
	// rule already had one (STR_NOT_ENOUGH_MONEY, STR_NOT_ENOUGH_CRAFT_SPACE, ...),
	// a plain sentence otherwise. Language::getString returns the id unchanged when
	// it is not a known key, so one lookup covers both.
	std::string text = "The host rejected your command.";
	if (!reason.empty() && game->getLanguage())
	{
		text = game->getLanguage()->getString(reason);
	}
	connectionTCP::sharedFailReason = text;
	game->pushState(new CoopState(COOP_DLG_SHARED_FAIL));
}

void init()
{
	if (g_inited) return;
	g_inited = true;
	registerCmd("buy", &buyValidate, &buyApply);
	// PRD-J05 economy commands (client -> host mutation requests).
	registerCmd("sell",        &sellValidate,        &sellApply);
	registerCmd("containment", &containmentValidate, &containmentApply);
	registerCmd("transfer",    &transferValidate,    &transferApply);
	// craft pilot picks (player-origin from either seat; the host resolves the list).
	registerCmd("craft_pilots", &craftPilotsValidate, &craftPilotsApply);
	// PRD-J06 research + manufacture commands (client -> host mutation requests).
	registerCmd("res_start",   &resStartValidate,    &resStartApply);
	registerCmd("res_alloc",   &resAllocValidate,    &resAllocApply);
	registerCmd("res_cancel",  &resCancelValidate,   &resCancelApply);
	registerCmd("man_start",   &manStartValidate,    &manStartApply);
	registerCmd("man_alloc",   &manAllocValidate,    &manAllocApply);
	registerCmd("man_cancel",  &manCancelValidate,   &manCancelApply);
	// PRD-J07 facilities / bases (client -> host mutation requests).
	registerCmd("fac_build",     &facBuildValidate,     &facBuildApply);
	registerCmd("fac_dismantle", &facDismantleValidate, &facDismantleApply);
	registerCmd("base_rename",   &baseRenameValidate,   &baseRenameApply);
	registerCmd("soldier_rename", &soldierRenameValidate, &soldierRenameApply);
	registerCmd("soldier_gift",   &soldierGiftValidate,   &soldierGiftApply);
	// A soldier transformation: the host runs it once and every machine adopts it.
	registerCmd("soldier_transform", &soldierTransformValidate, &soldierTransformApply);
	registerCmd("sack",          &sackValidate,         &sackApply);
	registerCmd("base_new",      &baseNewValidate,      &baseNewApply);
	// PRD-J07 base_destroyed: host-originated (retaliation, J04); replica-only apply.
	registerCmd("base_destroyed", &simAccept, &baseDestroyedApply);
	// PRD-J08 craft orders (any player -> host; last-command-wins by arrival order).
	registerCmd("craft_launch",   &craftOrderValidate,  &craftOrderApply);
	registerCmd("craft_retarget", &craftOrderValidate,  &craftOrderApply);
	registerCmd("craft_return",   &craftExistsValidate, &craftReturnApply);
	registerCmd("craft_patrol",   &craftExistsValidate, &craftPatrolApply);
	// the mind-shield and craft-weapon switches (player-origin from either seat; host-origin from the host's dogfight).
	registerCmd("fac_disable",          &facDisableValidate,         &facDisableApply);
	registerCmd("craft_weapon_disable", &craftWeaponDisableValidate, &craftWeaponDisableApply);

	// PRD-J09: shared-world squad assembly (mixed-owner deployment).
	registerCmd("craft_assign",   &craftAssignValidate, &craftAssignApply);
	// PRD-J09 GAP-5: shared-world craft equipment loadout (base-screen equip).
	registerCmd("craft_equip",    &craftEquipValidate,  &craftEquipApply);
	// A craft equipment template load (the whole loadout as one command).
	registerCmd("craft_loadout",  &craftLoadoutValidate, &craftLoadoutApply);
	// PRD-J09 GAP-5b: the sibling base-screen store mutators (arm/rearm a craft
	// weapon; change a soldier's armor - SoldierArmorState + CraftArmorState).
	registerCmd("craft_rearm",    &craftRearmValidate,  &craftRearmApply);
	registerCmd("soldier_armor",  &soldierArmorValidate, &soldierArmorApply);
	registerCmd("soldier_equip",  &soldierEquipValidate, &soldierEquipApply); // base-screen OK, player-origin, owner-gated
	registerCmd("equip_template", &equipTemplateValidate, &equipTemplateApply); // a template save, player-origin, last write wins
	registerCmd("craft_deployment", &craftDeploymentValidate, &craftDeploymentApply); // a craft type's generic deployment, player-origin, last write wins
	// manual promotion and nationality (player-origin from either seat; the host resolves the rank).
	registerCmd("soldier_rank",   &soldierRankValidate,   &soldierRankApply);
	registerCmd("soldier_nationality", &soldierNationalityValidate, &soldierNationalityApply);
	// psi training allocations (player-origin; own soldiers only, the host resolves the flag).
	registerCmd("soldier_psi_training", &soldierPsiTrainingValidate, &soldierPsiTrainingApply);
	// The training screens' flags (martial and psi): the host runs the training.
	registerCmd("soldier_training", &soldierTrainingValidate, &soldierTrainingApply);
	// The equipment layouts an inventory screen at a base produced (the host builds
	// every battle from them).
	registerCmd("soldier_layout", &soldierLayoutValidate, &soldierLayoutApply);
	// The base list order and a player's roster order, kept the same on every
	// machine (the mini base strip move and the roster screens' move up / down).
	registerCmd("base_move",      &baseMoveValidate,     &baseMoveApply);
	registerCmd("soldier_order",  &soldierOrderValidate, &soldierOrderApply);
	// Separate: a client's saved soldier layout or craft loadout slot, kept in
	// that player's profile on the host.
	registerCmd("equipment_template", &SeparateEcon::validateEquipmentTemplate,
		&SeparateEcon::applyEquipmentTemplate);
	// PRD-DF01 shared/replicated dogfights: host-originated membership broadcast
	// (df_open, full set + epoch each change; replica reconciles its render-only
	// windows). df_state (per-tick render frames) rides the SNAP_DOGFIGHT conflation
	// slot, NOT this reliable FIFO lane, so it has no registerCmd entry.
	registerCmd("df_open", &simAccept, &dfOpenApply);
	// PRD-DF02 replicated control: client->host dogfight command (stance / weapon /
	// disengage / self-destruct). Host applies to the authoritative sim in receive-order.
	registerCmd("df_cmd", &simAccept, &dfCmdApply);
	// PRD-J10 landing broker: host-origin prompt (seat-gated replica applier);
	// initiator-reported answer (host-only applier).
	registerCmd("land_prompt", &simAccept, &landPromptApply);
	registerCmd("land_reply",  &simAccept, &landReplyApply);
	registerCmd("land_close",  &simAccept, &landCloseApply);
	// Playtest (waypoint arrival): host-origin alert so replicas pop the "reached
	// destination" popup and clear the stale destination line + orphan waypoint marker.
	registerCmd("patrol_prompt", &simAccept, &patrolPromptApply);
	// Generic informational-alert replication: ONE command for every host-sim popup the
	// frozen replica would otherwise never see (UFO lost, low fuel, items arriving,
	// new-possibility dialogs, training finished, ...). Replica-only applier.
	registerCmd("alert", &simAccept, &alertApply);
	registerCmd("geo_event", &simAccept, &geoEventApply); // host-origin event result, replica-only
	// Host-authoritative alien-base discovery: a shared-world mutation, so the replica
	// must NOT roll its own (it used to, and the two could disagree).
	registerCmd("alien_base_found", &simAccept, &alienBaseFoundApply);
	// Missile-UFO base bombardment: facilities lost host-side must reach the replica
	// (shared world), and the "damaged but survived" dialog with it.
	registerCmd("base_damaged", &simAccept, &baseDamagedApply);
	// PRD-J04 host simulation-result mirrors (always-accept validator; appliers
	// run replica-side only).
	registerCmd("research_done",    &simAccept, &researchDoneApply);
	registerCmd("research_fx", &simAccept, &researchFxApply);
	registerCmd("research_grant", &simAccept, &researchGrantApply);
	registerCmd("research_effects", &simAccept, &researchEffectsApply);
	registerCmd("world_extras",     &simAccept, &worldExtrasApply);
	registerCmd("fac_done",         &simAccept, &facDoneApply);
	registerCmd("prod_done",        &simAccept, &prodDoneApply);
	registerCmd("transfer_arrived", &simAccept, &transferArrivedApply);
	registerCmd("prod_fx",          &simAccept, &prodFxApply); // host-origin, replica-only
	registerCmd("day_tick",         &simAccept, &dayTickApply);
	registerCmd("soldier_fx",       &simAccept, &soldierFxApply); // host-origin, replica-only
	registerCmd("unassign_wounded", &simAccept, &unassignWoundedApply); // host-origin, replica-only
	registerCmd("craft_lost",       &simAccept, &craftLostApply); // host-origin, replica-only (applied from the replica's geoscape)
	// the shared selection - the host resolves the list's state, replicas adopt it.
	registerCmd("sel_open", &simAccept, [](Game* g, Json::Value& p, Base*, int seat) { selApplyOp(g, p, seat, "sel_open"); });
	registerCmd("sel_set", &simAccept, [](Game* g, Json::Value& p, Base*, int seat) { selApplyOp(g, p, seat, "sel_set"); });
	registerCmd("sel_close", &simAccept, [](Game* g, Json::Value& p, Base*, int seat) { selApplyOp(g, p, seat, "sel_close"); });
	registerCmd("sel_sync", &simAccept, [](Game* g, Json::Value& p, Base*, int seat) { selApplyOp(g, p, seat, "sel_sync"); }); // host-origin
}

void broadcast(Game* game, const Json::Value& msg)
{
	if (!game || !game->getCoopMod()) return;
	// Transport is strictly 1:1 today (PRD-J01 audit); "broadcast" is a single
	// peer send. When N-player TCP lands, only this body iterates the client set.
	game->getCoopMod()->sendTCPPacketData(msg.toStyledString());
}

// PRD-DF01: df_state router (REPLICA only). df_state rides the SNAP_DOGFIGHT
// conflation slot (a raw top-level message, NOT the shared_apply lane), so
// connectionTCP::onTCPMessage hands it straight here. The GeoscapeState
// epoch-guards it against the reshuffle race and routes each frame to the
// matching render-only window by (craftId, craftType, ufoId).
void applyDogfightState(Game* game, const Json::Value& obj)
{
	if (!game || connectionTCP::getHost()) return; // host renders from its own sim
	GeoscapeState* gs = findGeoState(game);
	if (gs) gs->sharedApplyDogfightState(obj);
}

void beginRestreamHold();
void releaseHeldResults(Game* game);

bool onMessage(Game* game, const std::string& state, const Json::Value& obj)
{
	if (state == "shared_restream_mark" || state == "separate_restream_mark")
	{
		// The host just snapshotted its world for a restream (sharedResyncStream).
		if (!connectionTCP::getServerOwner())
			beginRestreamHold();
		return true;
	}
	if (state == "shared_cmd" || state == "separate_cmd")
	{
		// Only the host validates/applies commands; a replica ignores stray cmds.
		if (isHost())
		{
			PendingCmd pc;
			pc.cmd = obj.get("cmd", "").asString();
			pc.seq = obj.get("seq", 0).asInt();
			pc.seat = obj.get("seat", 0).asInt();
			pc.baseId = obj.get("baseId", -1).asInt();
			pc.baseKey = obj.get("baseKey", 0).asInt();
			pc.payload = obj["payload"];
			pc.remote = true;
			pc.separateProtocol = (state == "separate_cmd");
			std::lock_guard<std::mutex> lk(g_mx);
			g_cmdQ.push_back(std::move(pc));
		}
		return true;
	}
	if (state == "shared_apply" || state == "separate_apply")
	{
		// Replicas (and only replicas) adopt applied mutations. The host applied
		// at broadcast time and must never re-apply its own broadcast.
		if (!isHost())
		{
			std::lock_guard<std::mutex> lk(g_mx);
			g_applyQ.push_back(obj);
		}
		return true;
	}
	if (state == "shared_ok" || state == "separate_ok")
	{
		++g_okN; // informational: the mutation self-applies from shared_apply
		recordResult(obj.get("seq", 0).asInt(), 1); // an awaiting screen closes on it
		return true;
	}
	if (state == "shared_fail" || state == "separate_fail")
	{
		std::string reason = obj.get("reason", "").asString();
		++g_failN;
		setLastFail(reason);
		std::lock_guard<std::mutex> lk(g_mx);
		g_failQ.push_back({ reason, obj.get("seq", 0).asInt() });
		return true;
	}
	if (state == "shared_resync_request" || state == "separate_resync_request")
	{
		// PRD-J10: a replica's world checksum diverged from ours. Only the host
		// can answer; queue it for the main-thread pump (the restream serializes
		// the whole SavedGame, which must not race the apply drain).
		if (isHost())
		{
			std::lock_guard<std::mutex> lk(g_mx);
			++g_resyncServeQ;
		}
		return true;
	}
	return false;
}

void update(Game* game)
{
	if (!game) return;

	// 0) Replica: a restream's world was adopted (or its hold timed out). Hand the
	// results that arrived after its mark to the normal receive path, in arrival
	// order, ahead of the apply drain below.
	releaseHeldResults(game);

	// 1) Host: drain queued commands -> validate, debit, apply, broadcast.
	// the host fence - nothing is applied or broadcast while a
	// world streams (the client would discard it); the queue runs in order once the completion message has left.
	const bool fenced = isHost() && connectionTCP::coopWorldStreamBusy();
	if (fenced)
	{
		std::unique_lock<std::mutex> lk(g_mx);
		const bool queued = !g_cmdQ.empty();
		lk.unlock();
		if (queued)
			CoopDelta::battleEndRecordSet("fenceDeferredPasses",
				CoopDelta::battleEndRecord()["fenceDeferredPasses"].asInt() + 1);
	}
	for (; !fenced;)
	{
		PendingCmd pc;
		{
			std::lock_guard<std::mutex> lk(g_mx);
			if (g_cmdQ.empty()) break;
			pc = std::move(g_cmdQ.front());
			g_cmdQ.pop_front();
		}
		processHostCmd(game, pc);
	}

	// 2) Replica: drain queued applies -> setFunds + apply (held while a streamed world awaits adoption).
	for (; !g_applyHold;)
	{
		Json::Value ap;
		{
			std::lock_guard<std::mutex> lk(g_mx);
			if (g_applyQ.empty()) break;
			ap = std::move(g_applyQ.front());
			g_applyQ.pop_front();
		}
		processApply(game, ap);
	}

	// 3) Initiator: surface queued failures (one dialog per fail).
	for (;;)
	{
		std::pair<std::string, int> fail;
		bool have = false;
		{
			std::lock_guard<std::mutex> lk(g_mx);
			if (!g_failQ.empty()) { fail = g_failQ.front(); g_failQ.pop_front(); have = true; }
		}
		if (!have) break;
		showFail(game, fail.first);
		recordResult(fail.second, fail.first == "coop_sel_dup" ? 1 : -1); // the awaiting screen stays under the fail box; a duplicate is a success
	}

	// 4) Host: serve queued resync requests (PRD-J10). Re-stream the authoritative
	// world down the J02 bootstrap lane; the streamer is single-slot, so if it is
	// busy we drop the request - the replica's next mismatching checksum re-asks.
	for (;;)
	{
		bool have = false;
		{
			std::lock_guard<std::mutex> lk(g_mx);
			if (g_resyncServeQ > 0) { --g_resyncServeQ; have = true; }
		}
		if (!have) break;
		connectionTCP* coop = game->getCoopMod();
		if (!coop || !coop->getServerOwner()
			|| (!coop->isSharedCampaign() && !coop->isSeparateCampaign())) continue;
		++g_resyncReqN;
		Log(LOG_WARNING) << "[SHARED] resync requested by the replica; re-streaming"
			<< " the authoritative world";
		coop->sharedResyncStream();
	}
}

int submitLocalCmd(Game* game, const std::string& cmd, int baseId,
                    const Json::Value& payload)

{
	const bool separate = game && game->getCoopMod()
		&& (game->getCoopMod()->isSharedCampaign() || game->getCoopMod()->isSeparateCampaign())
		&& !game->getCoopMod()->isSharedCampaign();
	return submitCommandEngine(game, cmd, baseId, payload, separate);
}

int submitCommandEngine(Game* game, const std::string& cmd, int baseId,
	const Json::Value& payload, bool separateProtocol)
{
	if (!game) return 0;
	int seq = ++g_seqCounter;
	int seat = connectionTCP::localSeat();
	// Key every base the command names now, while the indexes still mean the
	// bases the player picked (a base_move can land before this command does).
	const int baseKey = baseKeyAt(game, baseId);
	Json::Value keyedPayload = payload;
	keyPayloadBaseRefs(game, keyedPayload);

	if (isHost())
	{
		// Host originates: queue for local validate+apply+broadcast (unified with
		// the client-cmd path in update(); host-origin skips the shared_cmd wire).
		PendingCmd pc;
		pc.cmd = cmd;
		pc.seq = seq;
		pc.seat = seat;
		pc.baseId = baseId;
		pc.baseKey = baseKey;
		pc.payload = keyedPayload;
		pc.remote = false;
		pc.separateProtocol = separateProtocol;
		std::lock_guard<std::mutex> lk(g_mx);
		g_cmdQ.push_back(std::move(pc));
	}
	else
	{
		// Replica: send the command to the host; mutate nothing locally.
		Json::Value msg;
		msg["state"] = separateProtocol ? "separate_cmd" : "shared_cmd";
		msg["cmd"] = cmd;
		msg["seq"] = seq;
		msg["seat"] = seat;
		msg["baseId"] = baseId;
		msg["baseKey"] = baseKey;
		msg["payload"] = keyedPayload;
		if (game->getCoopMod()) game->getCoopMod()->sendTCPPacketData(msg.toStyledString());
	}
	return seq;
}

// ---- screen keys, awaited answers, closing ----------
namespace
{
std::string screenKey(const char* screen, char variant, int baseIdx, const std::string& extra)
{
	return std::string(screen) + "|" + variant + "|" + std::to_string(baseIdx) + "|" + extra;
}

bool sharedGame(Game* game)
{
	return game && game->getCoopMod() && game->getCoopMod()->isSharedCampaign();
}
}

std::string sellKey(Game* game, Base* base, bool debrief, bool battlescapeOrigin)
{
	return screenKey("sell", debrief ? 'd' : battlescapeOrigin ? 'f' : 'n', baseIndex(game, base), "");
}

std::string xferKey(Game* game, Base* from, Base* to, bool debrief)
{
	return screenKey("xfer", debrief ? 'd' : 'n', baseIndex(game, from), std::to_string(baseIndex(game, to)));
}

std::string contKey(Game* game, Base* base, int prisonType, bool battlescapeOrigin)
{
	return screenKey("cont", battlescapeOrigin ? 'f' : 'n', baseIndex(game, base), "p" + std::to_string(prisonType));
}

// The Purchase/Hire screen; the one opened from "not enough equipment" has its own list.
std::string buyKey(Game* game, Base* base, bool reequip)
{
	return screenKey("buy", reequip ? 'r' : 'n', baseIndex(game, base), "");
}

void awaitResult(const std::string& key, int seq)
{
	std::lock_guard<std::mutex> lk(g_resMx);
	auto k = g_awaitByKey.find(key);
	if (k != g_awaitByKey.end()) g_awaitBySeq.erase(k->second);
	g_awaitByKey[key] = seq;
	g_awaitBySeq[seq] = key;
	g_resultByKey.erase(key);
}

bool awaiting(const std::string& key)
{
	std::lock_guard<std::mutex> lk(g_resMx);
	return g_awaitByKey.count(key) > 0;
}

int takeResult(const std::string& key)
{
	std::lock_guard<std::mutex> lk(g_resMx);
	auto r = g_resultByKey.find(key);
	if (r == g_resultByKey.end()) return 0;
	const int result = r->second;
	g_resultByKey.erase(r);
	return result;
}

void forgetResult(const std::string& key)
{
	std::lock_guard<std::mutex> lk(g_resMx);
	auto k = g_awaitByKey.find(key);
	if (k != g_awaitByKey.end()) { g_awaitBySeq.erase(k->second); g_awaitByKey.erase(k); }
	g_resultByKey.erase(key);
}

bool keepAfterSubmit(Game* game, const std::string& key, int seq, bool bound)
{
	if (!bound || !sharedGame(game)) return false; // a harness test command never ran init(): an immediate pop
	if (key.find("|f|") != std::string::npos) return true; // a forced screen stays until solved
	if (seq <= 0) return false;
	awaitResult(key, seq); // the screen waits for the host's answer
	return true;
}

bool sellScreenShouldClose(Game* game, Base* base, bool debrief, bool battlescapeOrigin)
{
	if (!sharedGame(game) || baseIndex(game, base) < 0) return false;
	if (!debrief && battlescapeOrigin) return storageSolved(base);
	return takeResult(sellKey(game, base, debrief, battlescapeOrigin)) == 1;
}

bool xferScreenShouldClose(Game* game, Base* from, Base* to, bool debrief)
{
	if (!sharedGame(game)) return false;
	return takeResult(xferKey(game, from, to, debrief)) == 1;
}

bool contScreenShouldClose(Game* game, Base* base, int prisonType, bool battlescapeOrigin)
{
	if (!sharedGame(game) || baseIndex(game, base) < 0) return false;
	if (battlescapeOrigin) return containmentSolved(base, prisonType);
	return takeResult(contKey(game, base, prisonType, battlescapeOrigin)) == 1;
}

// A Purchase/Hire screen closes on its OK answer.
bool buyScreenShouldClose(Game* game, Base* base, bool reequip)
{
	return sharedGame(game) && baseIndex(game, base) >= 0 && takeResult(buyKey(game, base, reequip)) == 1;
}

void resetSessionQueues()
{
	g_craftStage = Json::Value(Json::nullValue); // no staging window outlives its session
	size_t cmds = 0, applies = 0, fails = 0;
	{
		std::lock_guard<std::mutex> lk(g_mx);
		cmds = g_cmdQ.size();
		applies = g_applyQ.size();
		fails = g_failQ.size();
		g_cmdQ.clear();
		g_applyQ.clear();
		g_failQ.clear();
	}
	{
		std::lock_guard<std::mutex> lk(g_resMx);
		g_awaitBySeq.clear();
		g_awaitByKey.clear();
		g_resultByKey.clear();
	}
	const bool held = g_applyHold;
	g_applyHold = false;
	g_sel.clear(); g_selLocal.clear(); g_selCarry.clear(); // no shared list outlives its session
	Log(LOG_INFO) << "[SHARED] session reset: dropped " << cmds << " command(s), " << applies << " apply(s), " << fails
		<< " failure(s); apply hold was " << (held ? "on" : "off") << " (resetSessionQueues)";
}

// TestServer sel_state's read of the shared selection store (read-only).
Json::Value selectionSnapshot()
{
	Json::Value out(Json::objectValue);
	for (const auto& kv : g_sel) { out[kv.first] = selStateJson(kv.first); out[kv.first].removeMember("erased"); }
	return out;
}

// the host's seat-leave chokepoint (CoopSession::onClientDrop). The seat (< 0: every
// other seat, the transport is 1:1) leaves every list; an unviewed list is erased; nothing is broadcast (the peer is gone).
void onPeerLeft(int seat)
{
	const int me = connectionTCP::localSeat();
	int dropped = 0;
	for (auto it = g_sel.begin(); it != g_sel.end();)
	{
		for (auto v = it->second.viewers.begin(); v != it->second.viewers.end();)
			if (seat < 0 ? *v != me : *v == seat) { v = it->second.viewers.erase(v); ++dropped; } else ++v;
		if (it->second.viewers.empty()) it = g_sel.erase(it); else ++it;
	}
	Log(LOG_INFO) << "[SHARED] sel: seat " << seat << " left - " << dropped << " viewer(s) dropped, " << g_sel.size() << " list(s) left";
}

// ---- the SelectionBinder on SellState ----
namespace
{
std::string selRowKey(const TransferRow& row)
{
	switch (row.type)
	{
	case TRANSFER_ITEM: return "i:" + ((const RuleItem*)row.rule)->getType();
	case TRANSFER_SOLDIER: return "s:" + std::to_string(((const Soldier*)row.rule)->getId());
	case TRANSFER_CRAFT: return "c:" + std::to_string(((const Craft*)row.rule)->getId()) + ":" + ((const Craft*)row.rule)->getRules()->getType();
	case TRANSFER_SCIENTIST: return "sci";
	case TRANSFER_ENGINEER: return "eng";
	}
	return "";
}

// a Purchase row holds a rule, never a Soldier / Craft - its own row key.
std::string buyRowKey(const TransferRow& row)
{
	switch (row.type)
	{
	case TRANSFER_ITEM: return "i:" + ((const RuleItem*)row.rule)->getType();
	case TRANSFER_SOLDIER: return "h:" + ((const RuleSoldier*)row.rule)->getType();
	case TRANSFER_CRAFT: return "cr:" + ((const RuleCraft*)row.rule)->getType();
	case TRANSFER_SCIENTIST: return "sci";
	case TRANSFER_ENGINEER: return "eng";
	}
	return "";
}

// ---- Transfer and containment rows, label, highlight ----
// A row adopts min(list amount, its maximum) unless its own last edit is not answered yet. True = changed.
bool selAdopt(int& amount, const std::string& rk, int max, const SharedSel& m, const SelLocal& loc,
	const std::map<std::string, int>& sent)
{
	auto s = sent.find(rk), o = loc.ownSeen.find(rk), r = m.rows.find(rk);
	const int target = std::max(0, std::min(r == m.rows.end() ? 0 : r->second, max));
	if ((s != sent.end() && (o == loc.ownSeen.end() || o->second < s->second)) || amount == target) return false;
	amount = target;
	return true;
}

std::vector<std::string> selVisible(const std::vector<TransferRow>& items, const std::vector<int>& rows)
{
	std::vector<std::string> keys;
	for (int i : rows) keys.push_back(selRowKey(items[i]));
	return keys;
}

uint64_t selSig(const std::vector<int>& v)
{
	uint64_t h = 1469598103934665603ULL ^ v.size();
	for (int x : v) h = (h ^ (uint32_t)x) * 1099511628211ULL;
	return h;
}

// In a SHARED campaign a Sell / Transfer list gives up its last text row for good (TextList::
// setHeight re-places its down arrow and scrollbar and recounts its visible rows, TextList.cpp :542-549, :105-113,
// :982-990); the label (State-owned, hidden while alone) takes the line above the buttons (containment: its gap).
Text* selLayout(Game* game, State* screen, TextList* list, Surface* buttons, const char* cat, bool shrink)
{
	const Font* f = game->getMod()->getFont("FONT_SMALL");
	if (shrink) list->setHeight(list->getHeight() - (f->getHeight() + f->getSpacing()));
	Text* label = new Text(list->getWidth() - 2, f->getHeight(), list->getX() + 2, buttons->getY() - f->getHeight() - 1);
	screen->add(label, "text", cat);
	label->setVisible(false);
	Log(LOG_INFO) << "[SHARED] sel: " << cat << " list y " << list->getY() << " h " << list->getHeight() << " ("
		<< list->getVisibleRows() << " rows), presence label y " << label->getY() << ", buttons y " << buttons->getY();
	return label;
}

// The label names the other seats on the list; a visible row above 0 last edited by another seat is drawn in the
// screen's button2 colour, one that loses it goes back to the screen's updater; only on a rev / rows change.
void selPresent(Game* game, State* screen, const SharedSel& m, Text* label, std::string& shown, TextList* list,
	const char* cat, uint64_t rowsSig, uint64_t& drawnSig, std::map<std::string, int>& lit,
	const std::function<std::vector<std::string>()>& visibleKeys, const std::function<void(size_t)>& redraw)
{
	const int me = connectionTCP::localSeat();
	std::string names;
	for (int seat : m.viewers)
		if (seat != me && !connectionTCP::seatName(seat).empty()) names += (names.empty() ? "" : ", ") + connectionTCP::seatName(seat);
	if (label && names != shown)
		{ shown = names; label->setText(screen->tr("STR_COOP_ALSO_ON_SCREEN").arg(names)); label->setVisible(!names.empty()); }
	const uint64_t sig = (rowsSig ^ m.rev) * 1099511628211ULL + 1;
	if (sig == drawnSig) return;
	drawnSig = sig;
	const RuleInterface* ri = game->getMod()->getInterface(cat, false);
	const Element* b2 = ri ? ri->getElementOptional("button2") : nullptr;
	const std::vector<std::string> keys = visibleKeys();
	std::map<std::string, int> now;
	for (size_t v = 0; v < keys.size(); ++v)
	{
		auto r = m.rows.find(keys[v]), e = m.editors.find(keys[v]);
		if (b2 && r != m.rows.end() && r->second > 0 && e != m.editors.end() && e->second != me)
			{ list->setRowColor(v, b2->color); now[keys[v]] = 1; }
		else if (lit.count(keys[v])) redraw(v);
	}
	lit = now;
}
}

std::string SelectionBinder::keyOf(Game* game, SellState* screen)
{
	return sellKey(game, screen->_base, screen->_debriefingState != 0, screen->_origin == OPT_BATTLESCAPE);
}

Json::Value SelectionBinder::rowsOf(SellState* screen)
{
	Json::Value rows(Json::objectValue);
	for (const auto& row : screen->_items)
		if (row.amount > 0) rows[selRowKey(row)] = row.amount;
	return rows;
}

void SelectionBinder::sendOpen(const Json::Value& seed)
{
	_lastSent.clear();
	_acked = _seen = false;
	_openWant = g_selLocal[_key].openEchoes + 1; // acked once the list answers this open and lists this seat
	Json::Value p;
	p["key"] = _key; p["seed"] = seed;
	submitLocalCmd(_game, "sel_open", _baseIdx, p);
}

SelectionBinder::~SelectionBinder()
{
	if (!_opened || _carried || !connectionTCP::getCoopStatic() || !sharedGame(_game)) return;
	Json::Value p; p["key"] = _key;
	try { submitLocalCmd(_game, "sel_close", _baseIdx, p); } catch (...) {}
}

void SelectionBinder::open(Game* game, SellState* screen, bool bound)
{
	if (_opened || _inert) return;
	_game = game;
	if (!bound || !sharedGame(game)) { _inert = true; return; }
	_sell = screen; _opened = true;
	_label = selLayout(game, screen, screen->_lstItems, screen->_btnCancel, "sellMenu", true);
	_key = keyOf(game, screen);
	_baseIdx = baseIndex(game, screen->_base);
	auto c = g_selCarry.find(_key);
	if (c == g_selCarry.end()) { sendOpen(rowsOf(screen)); return; }
	_acked = c->second.first; // a refresh rebuild: adopt the list, send nothing
	_openWant = c->second.second;
	g_selCarry.erase(c);
}

void SelectionBinder::think(SellState* screen)
{
	const int baseIdx = _opened ? baseIndex(_game, screen->_base) : -1;
	if (baseIdx < 0) return; // inert, or the base is gone (the screen closes itself)
	const std::string key = keyOf(_game, screen);
	if (key != _key) { _key = key; _baseIdx = baseIdx; sendOpen(rowsOf(screen)); return; } // the indices shifted
	if (!_acked && g_selLocal[_key].openEchoes < _openWant) return; // keep the local (seeded) rows until answered
	auto it = g_sel.find(_key);
	if (it == g_sel.end() || !it->second.viewers.count(connectionTCP::localSeat())) { sendOpen(rowsOf(screen)); return; } // dropped
	_acked = true;
	const SharedSel& m = it->second;
	auto present = [&]() // the presence label and the highlight, after the rows
	{
		selPresent(_game, screen, m, _label, _labelShown, screen->_lstItems, "sellMenu", selSig(screen->_rows), _hlSig, _hlOn,
			[&]() { return selVisible(screen->_items, screen->_rows); },
			[&](size_t v) { const size_t s0 = screen->_sel; _applying = true; screen->_sel = v; screen->updateItemStrings();
				_applying = false; screen->_sel = s0; });
	};
	if (_seen && m.rev == _seenRev) { present(); return; }
	_seen = true; _seenRev = m.rev;
	// Each row adopts min(list amount, its maximum), unless its own last edit is not answered yet; then the
	// totals come from every row plus the list's rows this screen does not show (another seat's soldiers).
	const SelLocal& loc = g_selLocal[_key];
	std::set<std::string> shown;
	std::vector<size_t> changed;
	int64_t total = 0; double space = 0;
	for (size_t i = 0; i < screen->_items.size(); ++i)
	{
		TransferRow& row = screen->_items[i];
		const std::string rk = selRowKey(row);
		shown.insert(rk);
		auto sent = _lastSent.find(rk);
		auto seen = loc.ownSeen.find(rk);
		auto mr = m.rows.find(rk);
		const int target = std::max(0, std::min(mr == m.rows.end() ? 0 : mr->second, row.qtySrc));
		const bool pending = sent != _lastSent.end() && (seen == loc.ownSeen.end() || seen->second < sent->second);
		if (!pending && row.amount != target) { row.amount = target; changed.push_back(i); }
		if (row.amount <= 0) continue;
		total += (int64_t)row.cost * row.amount;
		if (row.type == TRANSFER_ITEM) space -= row.amount * ((const RuleItem*)row.rule)->getSize();
		else if (row.type == TRANSFER_SOLDIER && ((Soldier*)row.rule)->getArmor()->getStoreItem())
			space += row.amount * ((Soldier*)row.rule)->getArmor()->getStoreItem()->getSize();
	}
	for (const auto& r : m.rows)
	{
		if (shown.count(r.first)) continue;
		const RuleItem* rule = r.first.compare(0, 2, "i:") == 0 ? _game->getMod()->getItem(r.first.substr(2), false) : nullptr;
		if (rule) total += (int64_t)rule->getSellCostAdjusted(screen->_base, _game->getSavedGame()) * r.second;
		if (rule) space -= r.second * rule->getSize();
		for (auto* s : *screen->_base->getSoldiers())
			if (r.first == "s:" + std::to_string(s->getId()) && s->getArmor()->getStoreItem())
				space += r.second * s->getArmor()->getStoreItem()->getSize();
		for (auto* c : *screen->_base->getCrafts())
			if (r.first == "c:" + std::to_string(c->getId()) + ":" + c->getRules()->getType())
				total += (int64_t)c->getRules()->getSellCost() * r.second;
	}
	if (changed.empty() && total == screen->_total && std::fabs(space - screen->_spaceChange) < 1e-9) { present(); return; }
	screen->_total = total; screen->_spaceChange = space;
	// Redraw through the screen's own updater: each changed visible row, else one row for the totals.
	const size_t sel0 = screen->_sel;
	bool drawn = false;
	_applying = true;
	for (size_t v = 0; v < screen->_rows.size(); ++v)
		if (std::find(changed.begin(), changed.end(), (size_t)screen->_rows[v]) != changed.end())
			{ screen->_sel = v; screen->updateItemStrings(); drawn = true; }
	if (!drawn && !screen->_rows.empty())
		{ screen->_sel = sel0 < screen->_rows.size() ? sel0 : 0; screen->updateItemStrings(); }
	else if (!drawn)
	{
		screen->_txtSales->setText(screen->tr("STR_VALUE_OF_SALES").arg(Unicode::formatFunding(screen->_total)));
		if (screen->_debriefingState == 0 && Options::storageLimitsEnforced)
			screen->_btnOk->setVisible(!screen->_base->storesOverfull(screen->_spaceChange));
	}
	_applying = false; screen->_sel = sel0;
	present();
}

void SelectionBinder::localEdit(SellState* screen)
{
	if (!_opened || _applying || screen->_sel >= screen->_rows.size()) return;
	const TransferRow& row = screen->_items[screen->_rows[screen->_sel]];
	const std::string rk = selRowKey(row);
	Json::Value p;
	p["key"] = _key; p["row"] = rk; p["amount"] = row.amount;
	p["eseq"] = _lastSent[rk] = ++g_selEseq;
	submitLocalCmd(_game, "sel_set", _baseIdx, p);
}

void SelectionBinder::carryOver()
{
	if (!_opened) return;
	g_selCarry[_key] = { _acked, _openWant };
	_carried = true;
}

void SelectionBinder::stamp(Json::Value& payload)
{
	if (!_opened) return; // a harness test command never opened one: its confirm carries no selKey
	auto it = g_sel.find(_key);
	payload["selKey"] = _key;
	payload["selRev"] = Json::UInt(it == g_sel.end() ? 0 : it->second.rev);
	payload["selRows"] = _sell ? rowsOf(_sell) : _xfer ? rowsOf(_xfer) : _buy ? rowsOf(_buy) : rowsOf(_cont);
	if (_buy && _key.compare(0, 6, "buy|r|") == 0) payload["reequip"] = true;
	if (_key.find("|d|") == std::string::npos || (!_sell && !_xfer)) return;
	payload["selCaps"] = Json::Value(Json::objectValue); // page 3: each row's recovered count
	for (const auto& row : _sell ? _sell->_items : _xfer->_items)
		if (row.type == TRANSFER_ITEM) payload["selCaps"][selRowKey(row)] = row.qtySrc;
}

bool SelectionBinder::listed() const
{
	auto it = _opened ? g_sel.find(_key) : g_sel.end();
	return it != g_sel.end() && !it->second.rows.empty();
}

// ---- the binder on Transfer and containment ----
std::string SelectionBinder::keyOf(Game* game, TransferItemsState* screen)
	{ return xferKey(game, screen->_baseFrom, screen->_baseTo, screen->_debriefingState != 0); }
std::string SelectionBinder::keyOf(Game* game, ManageAlienContainmentState* screen)
	{ return contKey(game, screen->_base, screen->_prisonType, screen->_origin == OPT_BATTLESCAPE); }

Json::Value SelectionBinder::rowsOf(TransferItemsState* screen)
{
	Json::Value rows(Json::objectValue);
	for (const auto& row : screen->_items)
		if (row.amount > 0) rows[selRowKey(row)] = row.amount;
	return rows;
}

Json::Value SelectionBinder::rowsOf(ManageAlienContainmentState* screen)
{
	Json::Value rows(Json::objectValue);
	for (size_t i = 0; i < screen->_qtys.size() && i < screen->_aliens.size(); ++i)
		if (screen->_qtys[i] > 0) rows["i:" + screen->_aliens[i]] = screen->_qtys[i];
	return rows;
}

void SelectionBinder::open(Game* game, TransferItemsState* screen, bool bound)
{
	if (_opened || _inert) return;
	if (!bound || !sharedGame(game)) { _inert = true; return; }
	_game = game; _xfer = screen; _opened = true;
	_label = selLayout(game, screen, screen->_lstItems, screen->_btnCancel, "transferMenu", true);
	_key = keyOf(game, screen); _baseIdx = baseIndex(game, screen->_baseFrom);
	auto c = g_selCarry.find(_key);
	if (c == g_selCarry.end()) { sendOpen(rowsOf(screen)); return; }
	_acked = c->second.first; _openWant = c->second.second; // a refresh rebuild: adopt the list, send nothing
	g_selCarry.erase(c);
}

void SelectionBinder::open(Game* game, ManageAlienContainmentState* screen, bool bound)
{
	if (_opened || _inert) return;
	if (!bound || !sharedGame(game)) { _inert = true; return; }
	_game = game; _cont = screen; _opened = true; // rebuilds in place: never carried over
	_label = selLayout(game, screen, screen->_lstAliens, screen->_btnCancel, "manageContainment", false);
	_key = keyOf(game, screen); _baseIdx = baseIndex(game, screen->_base);
	sendOpen(rowsOf(screen));
}

void SelectionBinder::think(TransferItemsState* screen)
{
	const int baseIdx = _opened && baseIndex(_game, screen->_baseTo) >= 0 ? baseIndex(_game, screen->_baseFrom) : -1;
	if (baseIdx < 0) return; // inert, or a base is gone (the screen leaves itself)
	const std::string key = keyOf(_game, screen);
	if (key != _key) { _key = key; _baseIdx = baseIdx; sendOpen(rowsOf(screen)); return; } // the indices shifted
	if (!_acked && g_selLocal[_key].openEchoes < _openWant) return;
	auto it = g_sel.find(_key);
	if (it == g_sel.end() || !it->second.viewers.count(connectionTCP::localSeat())) { sendOpen(rowsOf(screen)); return; }
	_acked = true;
	const SharedSel& m = it->second;
	if (!_seen || m.rev != _seenRev)
	{
		// The rows adopt the list; totals as increase/decreaseByValue keep them (:1386-:1546), + hidden rows.
		_seen = true; _seenRev = m.rev;
		std::set<std::string> shown; std::vector<size_t> changed;
		int total = 0, pQty = 0, cQty = 0, aQty = 0; double iQty = 0;
		for (size_t i = 0; i < screen->_items.size(); ++i)
		{
			TransferRow& row = screen->_items[i];
			shown.insert(selRowKey(row));
			if (selAdopt(row.amount, selRowKey(row), row.qtySrc, m, g_selLocal[_key], _lastSent)) changed.push_back(i);
			if (row.amount <= 0) continue;
			if (row.type == TRANSFER_CRAFT)
			{
				Craft* c = (Craft*)row.rule;
				++cQty; pQty += c->getNumTotalSoldiers(); iQty += c->getTotalItemStorageSize();
				total += !Options::canTransferCraftsWhileAirborne || c->getStatus() != "STR_OUT" ? row.cost : 0;
				continue;
			}
			total += row.cost * row.amount;
			if (row.type != TRANSFER_ITEM) pQty += row.amount;
			else { iQty += row.amount * ((RuleItem*)row.rule)->getSize(); aQty += ((RuleItem*)row.rule)->isAlien() ? row.amount : 0; }
		}
		for (const auto& r : m.rows)
			for (auto* s : *screen->_baseFrom->getSoldiers())
				if (!shown.count(r.first) && r.first == "s:" + std::to_string(s->getId())) { ++pQty; total += (int)(5 * screen->_distance); }
		screen->_total = total; screen->_pQty = pQty; screen->_cQty = cQty; screen->_aQty = aQty; screen->_iQty = iQty;
		const size_t sel0 = screen->_sel; _applying = true;
		for (size_t v = 0; v < screen->_rows.size(); ++v)
			if (std::find(changed.begin(), changed.end(), (size_t)screen->_rows[v]) != changed.end())
				{ screen->_sel = v; screen->updateItemStrings(); }
		_applying = false; screen->_sel = sel0;
	}
	selPresent(_game, screen, m, _label, _labelShown, screen->_lstItems, "transferMenu", selSig(screen->_rows), _hlSig, _hlOn,
		[&]() { return selVisible(screen->_items, screen->_rows); },
		[&](size_t v) { const size_t s0 = screen->_sel; _applying = true; screen->_sel = v; screen->updateItemStrings();
			_applying = false; screen->_sel = s0; });
}

void SelectionBinder::think(ManageAlienContainmentState* screen)
{
	const int baseIdx = _opened ? baseIndex(_game, screen->_base) : -1;
	if (baseIdx < 0) return; // inert, or the base is gone
	const std::string key = keyOf(_game, screen);
	if (key != _key) { _key = key; _baseIdx = baseIdx; sendOpen(rowsOf(screen)); return; } // the indices shifted
	if (!_acked && g_selLocal[_key].openEchoes < _openWant) return;
	auto it = g_sel.find(_key);
	if (it == g_sel.end() || !it->second.viewers.count(connectionTCP::localSeat())) { sendOpen(rowsOf(screen)); return; }
	_acked = true;
	const SharedSel& m = it->second;
	// init() and a refresh rebuild the list in place (resetListAndTotals zeroes and repaints every row): re-apply, re-draw.
	if (selSig(screen->_qtys) != _contSig) { _seen = false; _hlSig = 0; }
	if (!_seen || m.rev != _seenRev)
	{
		_seen = true; _seenRev = m.rev;
		std::vector<size_t> changed; int sold = 0;
		for (size_t i = 0; i < screen->_qtys.size() && i < screen->_aliens.size(); ++i)
		{
			const int stock = screen->_base->getStorageItems()->getItem(screen->_aliens[i]);
			if (selAdopt(screen->_qtys[i], "i:" + screen->_aliens[i], stock, m, g_selLocal[_key], _lastSent)) changed.push_back(i);
			sold += screen->_qtys[i];
		}
		screen->_aliensSold = sold; // updateStrings reads it for the space / button totals
		const size_t sel0 = screen->_sel; _applying = true;
		for (size_t i : changed) { screen->_sel = i; screen->updateStrings(); }
		_applying = false; screen->_sel = sel0;
		_contSig = selSig(screen->_qtys);
	}
	selPresent(_game, screen, m, _label, _labelShown, screen->_lstAliens, "manageContainment",
		selSig(std::vector<int>(1, (int)screen->_qtys.size())), _hlSig, _hlOn,
		[&]() { std::vector<std::string> k; for (const auto& a : screen->_aliens) k.push_back("i:" + a); return k; },
		[&](size_t v) { const size_t s0 = screen->_sel; _applying = true; screen->_sel = v; screen->updateStrings();
			_applying = false; screen->_sel = s0; });
}

void SelectionBinder::localEdit(TransferItemsState* screen)
{
	if (!_opened || _applying || screen->_sel >= screen->_rows.size()) return;
	const TransferRow& row = screen->_items[screen->_rows[screen->_sel]];
	const std::string rk = selRowKey(row);
	Json::Value p;
	p["key"] = _key; p["row"] = rk; p["amount"] = row.amount;
	p["eseq"] = _lastSent[rk] = ++g_selEseq;
	submitLocalCmd(_game, "sel_set", _baseIdx, p);
}

void SelectionBinder::localEdit(ManageAlienContainmentState* screen)
{
	if (!_opened || _applying || screen->_sel >= screen->_qtys.size() || screen->_sel >= screen->_aliens.size()) return;
	const std::string rk = "i:" + screen->_aliens[screen->_sel];
	Json::Value p;
	p["key"] = _key; p["row"] = rk; p["amount"] = screen->_qtys[screen->_sel];
	p["eseq"] = _lastSent[rk] = ++g_selEseq;
	submitLocalCmd(_game, "sel_set", _baseIdx, p);
	_contSig = selSig(screen->_qtys); // the screen's own edit, not a rebuild
}

// ---- the binder on Purchase/Hire ----------
// Both variants (normal buy|n|, reequip buy|r|); rows keyed by buyRowKey (a Purchase row holds a rule).
std::string SelectionBinder::keyOf(Game* game, PurchaseState* screen)
	{ return buyKey(game, screen->_base, screen->_parent != nullptr); }

Json::Value SelectionBinder::rowsOf(PurchaseState* screen)
{
	Json::Value rows(Json::objectValue);
	for (const auto& row : screen->_items)
		if (row.amount > 0) rows[buyRowKey(row)] = row.amount;
	return rows;
}

void SelectionBinder::open(Game* game, PurchaseState* screen, bool bound)
{
	if (_opened || _inert) return;
	if (!bound || !sharedGame(game)) { _inert = true; return; } // the buy test command never runs init()
	_game = game; _buy = screen; _opened = true;
	_label = selLayout(game, screen, screen->_lstItems, screen->_btnCancel, "buyMenu", true); // the Sell / Transfer list layout, by analogy
	_key = keyOf(game, screen); _baseIdx = baseIndex(game, screen->_base);
	auto c = g_selCarry.find(_key);
	if (c == g_selCarry.end()) { sendOpen(rowsOf(screen)); return; } // seed = the reequip pre-fill only
	_acked = c->second.first; _openWant = c->second.second; // a refresh rebuild: adopt the list, send nothing
	g_selCarry.erase(c);
}

void SelectionBinder::think(PurchaseState* screen)
{
	const int baseIdx = _opened ? baseIndex(_game, screen->_base) : -1;
	if (baseIdx < 0) return; // inert, or the base is gone (the screen leaves itself)
	const std::string key = keyOf(_game, screen);
	if (key != _key) { _key = key; _baseIdx = baseIdx; sendOpen(rowsOf(screen)); return; } // the indices shifted
	if (!_acked && g_selLocal[_key].openEchoes < _openWant) return;
	auto it = g_sel.find(_key);
	if (it == g_sel.end() || !it->second.viewers.count(connectionTCP::localSeat())) { sendOpen(rowsOf(screen)); return; }
	_acked = true;
	const SharedSel& m = it->second;
	if (!_seen || m.rev != _seenRev)
	{
		// Each row adopts the list's amount with no local cap - qtySrc is the base's stock, not a maximum - unless its
		// own last edit is unanswered. The five totals increaseByValue gates on come from every row, hidden or
		// filtered too, plus the list's rows this screen does not build, at their rule's cost and size.
		_seen = true; _seenRev = m.rev;
		Mod* mod = _game->getMod();
		std::set<std::string> shown; std::vector<size_t> changed;
		int64_t total = 0; int pQty = 0, cQty = 0; double iQty = 0; std::map<int, int> prison;
		auto addItem = [&](const RuleItem* r, int n) { iQty += n * r->getSize(); if (r->isAlien()) prison[r->getPrisonType()] += n; };
		for (size_t i = 0; i < screen->_items.size(); ++i)
		{
			TransferRow& row = screen->_items[i];
			const std::string rk = buyRowKey(row);
			shown.insert(rk);
			if (selAdopt(row.amount, rk, INT_MAX, m, g_selLocal[_key], _lastSent)) changed.push_back(i);
			if (row.amount <= 0) continue;
			total += (int64_t)row.cost * row.amount;
			if (row.type == TRANSFER_ITEM) addItem((const RuleItem*)row.rule, row.amount);
			else if (row.type == TRANSFER_CRAFT) cQty += row.amount;
			else pQty += row.amount;
		}
		for (const auto& r : m.rows)
		{
			if (shown.count(r.first)) continue;
			const std::string type = r.first.substr(r.first.find(':') + 1);
			if (r.first == "sci" || r.first == "eng")
				{ total += (int64_t)r.second * (r.first == "sci" ? mod->getHireScientistCost() : mod->getHireEngineerCost()); pQty += r.second; }
			else if (const RuleSoldier* rs = r.first.compare(0, 2, "h:") == 0 ? mod->getSoldier(type, false) : nullptr)
				{ total += (int64_t)r.second * rs->getBuyCost(); pQty += r.second; }
			else if (const RuleCraft* rc = r.first.compare(0, 3, "cr:") == 0 ? mod->getCraft(type, false) : nullptr)
				{ total += (int64_t)r.second * rc->getBuyCost(); cQty += r.second; }
			else if (const RuleItem* ri = r.first.compare(0, 2, "i:") == 0 ? mod->getItem(type, false) : nullptr)
				{ total += (int64_t)r.second * ri->getBuyCostAdjusted(screen->_base, _game->getSavedGame()); addItem(ri, r.second); }
		}
		const bool redraw = !changed.empty() || total != screen->_total || std::fabs(iQty - screen->_iQty) > 1e-9;
		screen->_total = (int)total; screen->_pQty = pQty; screen->_cQty = cQty; screen->_iQty = iQty; screen->_iPrisonQty = prison;
		const size_t sel0 = screen->_sel;
		bool drawn = false;
		_applying = true;
		for (size_t v = 0; redraw && v < screen->_rows.size(); ++v) // each changed visible row, else one row for the totals
			if (std::find(changed.begin(), changed.end(), (size_t)screen->_rows[v]) != changed.end())
				{ screen->_sel = v; screen->updateItemStrings(); drawn = true; }
		if (redraw && !drawn && !screen->_rows.empty())
			{ screen->_sel = sel0 < screen->_rows.size() ? sel0 : 0; screen->updateItemStrings(); }
		else if (redraw && !drawn) // no visible row: the two totals texts as updateItemStrings sets them (PurchaseState :1497, :1517-:1526)
		{
			std::ostringstream ss;
			ss << screen->_base->getUsedStores();
			if (std::abs(screen->_iQty) > 0.05)
				ss << "(" << (screen->_iQty > 0.05 ? "+" : "") << std::fixed << std::setprecision(1) << screen->_iQty << ")";
			ss << ":" << screen->_base->getAvailableStores();
			screen->_txtPurchases->setText(screen->tr("STR_COST_OF_PURCHASES").arg(Unicode::formatFunding(screen->_total)));
			screen->_txtSpaceUsed->setText(screen->tr("STR_SPACE_USED").arg(ss.str()));
		}
		_applying = false; screen->_sel = sel0;
	}
	selPresent(_game, screen, m, _label, _labelShown, screen->_lstItems, "buyMenu", selSig(screen->_rows), _hlSig, _hlOn,
		[&]() { std::vector<std::string> k; for (int i : screen->_rows) k.push_back(buyRowKey(screen->_items[i])); return k; },
		[&](size_t v) { const size_t s0 = screen->_sel; _applying = true; screen->_sel = v; screen->updateItemStrings();
			_applying = false; screen->_sel = s0; });
}

void SelectionBinder::localEdit(PurchaseState* screen)
{
	if (!_opened || _applying || screen->_sel >= screen->_rows.size()) return;
	const TransferRow& row = screen->_items[screen->_rows[screen->_sel]];
	const std::string rk = buyRowKey(row);
	Json::Value p;
	p["key"] = _key; p["row"] = rk; p["amount"] = row.amount;
	p["eseq"] = _lastSent[rk] = ++g_selEseq;
	submitLocalCmd(_game, "sel_set", _baseIdx, p);
}

Stats stats()
{
	Stats s;
	s.cmd = g_cmdN.load();
	s.ok = g_okN.load();
	s.fail = g_failN.load();
	s.apply = g_applyN.load();
	s.unknown = g_unknownN.load();
	return s;
}

std::string lastFailReason()
{
	std::lock_guard<std::mutex> lk(g_failMx);
	return g_lastFail;
}

// read-only, TestServer shared_stats.applyQueued.
int applyQueueDepth() { std::lock_guard<std::mutex> lk(g_mx); return (int)g_applyQ.size(); }
bool applyHoldOn() { return g_applyHold; } // read-only, TestServer shared_stats.applyHold

void resetStats()
{
	g_cmdN = 0; g_okN = 0; g_failN = 0; g_applyN = 0; g_unknownN = 0;
	std::lock_guard<std::mutex> lk(g_failMx);
	g_lastFail.clear();
}

// ---- PRD-J04 host sim-result broadcasts --------------------------------------
// All gate on isSharedCampaign() && host; each rides submitLocalCmd (host-origin),
// which validate(accept)+apply(host no-op)+broadcasts shared_apply to the replica.
namespace {
bool sharedHost(Game* game)
{
	return game && game->getCoopMod() && (game->getCoopMod()->isSharedCampaign() || game->getCoopMod()->isSeparateCampaign())
		&& game->getCoopMod()->getServerOwner();
}

// The SHARED host only: research_fx, prod_fx, geo_event, research_grant, soldier_fx and craft_lost. A Separate replica
// takes the same results from its own commands (research_effects, prod_done, the replicated event window, day_tick).
bool sharedCampaignHost(Game* game)
{
	return game && game->getCoopMod() && game->getCoopMod()->isSharedCampaign() && game->getCoopMod()->getServerOwner();
}

}

void hostResearchDone(Game* game, int baseId, const std::string& research,
                      const std::string& bonus, const std::string& newResearch,
                      const std::string& corpse)
{
	if (!sharedHost(game)) return;
	Json::Value p;
	p["research"] = research;
	p["bonus"] = bonus;
	p["newResearch"] = newResearch;
	p["corpse"] = corpse;
	const GameTime* hostTime = game->getSavedGame()->getTime(); // the host's date stamps the replica's diary
	Json::Value hostDate(Json::arrayValue); hostDate.append(hostTime->getYear()); hostDate.append(hostTime->getMonth()); hostDate.append(hostTime->getDay());
	p["date"] = hostDate;
	submitLocalCmd(game, "research_done", baseId, p);
}

// ---- research_fx - the host side ----------------------------------------------------
// time1Day marks the world right before a base's completion block (3a) and diffs it right after
// handlePrimaryResearchSideEffects (3j-3m): one synchronous chain, so the diff is exactly this base's completion effects,
// incl. 3j removals and refunds in every base. 3l (spawned events) stays host-only.
Json::Value researchFxMark(Game* game, bool armed)
{
	if (!armed || !sharedCampaignHost(game) || !game->getSavedGame()) return Json::Value(Json::nullValue);
	SavedGame* save = game->getSavedGame();
	Json::Value m(Json::objectValue), bases(Json::arrayValue), transfers(Json::arrayValue), ids(Json::objectValue);
	for (auto* b : *save->getBases())
	{
		Json::Value e(Json::objectValue), stores(Json::objectValue), projects(Json::arrayValue);
		for (const auto& kv : *b->getStorageItems()->getContents()) stores[kv.first->getType()] = kv.second;
		for (auto* rp : b->getResearch()) projects.append(rp->getRules()->getName());
		e["stores"] = stores; e["projects"] = projects;
		bases.append(e);
		transfers.append((int)b->getTransfers()->size());
	}
	for (const auto& kv : save->getAllIds()) ids[kv.first] = kv.second;
	m["bases"] = bases; m["transfers"] = transfers; m["ids"] = ids;
	return m;
}

void hostResearchFx(Game* game, int baseId, const Json::Value& mark)
{
	if (mark.isNull() || !sharedCampaignHost(game) || !game->getSavedGame()) return;
	const Json::Value now = researchFxMark(game, true);
	const std::vector<Base*>& bases = *game->getSavedGame()->getBases();
	Json::Value p(Json::objectValue), removed(Json::arrayValue), stores(Json::arrayValue), transfers(Json::arrayValue),
		ids(Json::objectValue);
	for (Json::ArrayIndex i = 0; i < now["bases"].size() && i < mark["bases"].size() && i < bases.size(); ++i)
	{
		const Json::Value& was = mark["bases"][i];
		const Json::Value& cur = now["bases"][i];
		std::set<std::string> left; // removed: in the mark, absent now (the finished topic too; the replica skips it)
		for (const auto& n : cur["projects"]) left.insert(n.asString());
		for (const auto& n : was["projects"])
			if (!left.count(n.asString()))
			{
				Json::Value r(Json::objectValue);
				r["base"] = (int)i; r["name"] = n;
				removed.append(r);
			}
		Json::Value items(Json::objectValue), st(Json::objectValue); // stores: changed items only, absolute, 0 when gone
		for (const auto& k : was["stores"].getMemberNames())
			if (!cur["stores"].isMember(k)) items[k] = 0;
		for (const auto& k : cur["stores"].getMemberNames())
			if (was["stores"][k] != cur["stores"][k]) items[k] = cur["stores"][k];
		st["base"] = (int)i; st["items"] = items;
		if (!items.empty()) stores.append(st);
		const std::vector<Transfer*>& tv = *bases[i]->getTransfers(); // transfers: appended past the mark (3k)
		for (size_t t = mark["transfers"][i].asUInt(); t < tv.size(); ++t)
		{
			if (tv[t]->getType() != TRANSFER_ITEM || !tv[t]->getItems())
			{
				static bool logged = false;
				if (!logged)
					Log(LOG_WARNING) << "[SHARED] research_fx: a new non-item transfer (type " << (int)tv[t]->getType()
						<< ") is not mirrored (logged once)";
				logged = true;
				continue;
			}
			Json::Value tj(Json::objectValue);
			tj["base"] = (int)i; tj["item"] = tv[t]->getItems()->getType(); tj["qty"] = tv[t]->getQuantity();
			tj["hours"] = tv[t]->getHours();
			transfers.append(tj);
		}
	}
	for (const auto& k : now["ids"].getMemberNames()) // ids: changed or new counters (3m)
		if (!mark["ids"].isMember(k) || mark["ids"][k] != now["ids"][k]) ids[k] = now["ids"][k];
	p["removed"] = removed; p["stores"] = stores; p["transfers"] = transfers; p["ids"] = ids;
	submitLocalCmd(game, "research_fx", baseId, p);
}

void hostResearchSideEffects(Game* game, const std::vector<const RuleResearch*>& topics,
                             Base* base)
{
	SavedGame* save = game ? game->getSavedGame() : nullptr;
	if (!save || topics.empty()) return;
	Mod* mod = game->getMod();
	if (!sharedHost(game) || !base)
	{
		save->handlePrimaryResearchSideEffects(topics, mod, base);
		return;
	}
	// Every base's projects before the call. A base never runs two projects of
	// one topic, so (base index, topic) names a project.
	struct Project { int baseIdx; std::string research; bool refund; };
	std::vector<Project> before;
	auto& bases = *save->getBases();
	int baseIdx = -1;
	for (size_t i = 0; i < bases.size(); ++i)
	{
		if (bases[i] == base) baseIdx = (int)i;
		for (ResearchProject* proj : bases[i]->getResearch())
		{
			const RuleResearch* rule = proj->getRules();
			// Base::removeResearch refunds the needed item of an unfinished project.
			before.push_back({ (int)i, rule->getName(),
				!proj->isFinished() && rule->needItem() && rule->destroyItem() });
		}
	}
	const size_t transfersBefore = base->getTransfers()->size();
	save->handlePrimaryResearchSideEffects(topics, mod, base);
	if (baseIdx < 0) return;

	Json::Value removed(Json::arrayValue);
	for (const auto& proj : before)
	{
		if (findResearchProject(bases[proj.baseIdx], proj.research)) continue;
		Json::Value r;
		r["baseIdx"] = proj.baseIdx;
		r["research"] = proj.research;
		r["refund"] = proj.refund;
		removed.append(r);
	}
	// handlePrimaryResearchSideEffects only appends the spawned item transfers.
	Json::Value spawned(Json::arrayValue);
	const auto& transfers = *base->getTransfers();
	for (size_t i = transfersBefore; i < transfers.size(); ++i)
	{
		const Transfer* t = transfers[i];
		if (!t->getItems()) continue;
		Json::Value s;
		s["item"] = t->getItems()->getType();
		s["qty"] = t->getQuantity();
		s["hours"] = t->getHours();
		s["owner"] = t->getOwnerPlayerName();
		spawned.append(s);
	}
	if (removed.empty() && spawned.empty()) return;
	Json::Value p;
	p["removed"] = removed;
	p["transfers"] = spawned;
	submitLocalCmd(game, "research_effects", baseIdx, p);
}

void hostFacilityDone(Game* game, int baseId, int x, int y, const std::string& facilityType)
{
	if (!sharedHost(game)) return;
	Json::Value p;
	p["x"] = x;
	p["y"] = y;
	p["type"] = facilityType;
	submitLocalCmd(game, "fac_done", baseId, p);
}

void hostProductionDone(Game* game, int baseId, const std::string& manufacture,
                        int units, int progress, bool sell,
                        const std::vector<int>& craftIds, bool batchDone,
                        const std::vector<Soldier*>& soldiers)
{
	if (!sharedHost(game)) return;
	Json::Value p;
	p["manufacture"] = manufacture;
	p["units"] = units;
	p["progress"] = progress;
	// The units this step made; the replica removes the Production only when
	// the batch is done.
	p["final"] = batchDone;
	// GAP-6b: carry the host Production's SELL flag so the replica materializes
	// exactly what the host did (sold -> funds only, nothing to stores).
	p["sell"] = sell;
	// the finished production's random-production list, absolute (GeoscapeState removes the production after this call)
	if (Base* b = resolveBase(game, baseId))
		if (Production* pr = findProduction(b, manufacture))
			if (!pr->getRules()->getRandomProducedItems().empty())
			{
				p["random"] = Json::Value(Json::objectValue);
				for (const auto& kv : pr->getRandomProductionInfo()) p["random"][kv.first] = kv.second;
			}
	// The crafts the host built, by id. Without them the replica minted ids from
	// its own counter, which falls behind whenever the host builds a unit and a
	// purchase lands before the batch finishes.
	if (game->getMod())
		if (const RuleManufacture* rule = game->getMod()->getManufacture(manufacture, false))
			if (rule->getProducedCraft())
			{
				Json::Value ids(Json::arrayValue);
				for (int id : craftIds) ids.append(id);
				p["craftIds"] = ids;
			}
	// The soldiers it spawned, whole (id, name, stats, owner): the replica takes
	// them instead of rolling its own.
	if (!soldiers.empty())
	{
		Json::Value spawned(Json::arrayValue);
		for (Soldier* s : soldiers) spawned.append(serializeSoldier(game, s));
		p["soldiers"] = spawned;
	}
	submitLocalCmd(game, "prod_done", baseId, p);
}

void hostTransferArrived(Game* game, int baseId, const Json::Value& arrived)
{
	if (!sharedHost(game)) return;
	if (!arrived.isArray() || arrived.empty()) return;
	Json::Value p;
	p["arrived"] = arrived;
	submitLocalCmd(game, "transfer_arrived", baseId, p);
}

void hostBaseDestroyed(Game* game, int baseId, const std::string& name, bool missiles)
{
	if (!sharedHost(game)) return;
	g_sel.clear(); // base indices shift - every binder re-keys on its next think()
	Json::Value p;
	p["name"] = name;
	p["missiles"] = missiles;
	submitLocalCmd(game, "base_destroyed", baseId, p);
}

// ---- PRD-J08 public API --------------------------------------------------------

namespace {

// Index of the base holding @a craft (baseId of a craft order), or -1.
int craftBaseIndex(Game* game, const Craft* craft)
{
	SavedGame* save = game ? game->getSavedGame() : nullptr;
	if (!save) return -1;
	auto* bases = save->getBases();
	for (int i = 0; i < (int)bases->size(); ++i)
		for (auto* c : *(*bases)[i]->getCrafts())
			if (c == craft) return i;
	return -1;
}

// Serialize @a target into an order payload (shared real ids; lon/lat always
// carried so a "point" fallback and the UI echo stay possible).
void describeTarget(Game* game, Target* target, Json::Value& p)
{
	p["lon"] = target->getLongitude();
	p["lat"] = target->getLatitude();
	if (auto* u = dynamic_cast<Ufo*>(target))
	{
		p["targetType"] = "ufo";
		p["targetId"] = u->getId();
	}
	else if (auto* s = dynamic_cast<MissionSite*>(target))
	{
		p["targetType"] = "site";
		p["targetId"] = s->getId();
	}
	else if (auto* ab = dynamic_cast<AlienBase*>(target))
	{
		p["targetType"] = "abase";
		p["targetId"] = ab->getId();
	}
	else if (auto* b = dynamic_cast<Base*>(target))
	{
		p["targetType"] = "xbase";
		SavedGame* save = game->getSavedGame();
		auto* bases = save->getBases();
		for (int i = 0; i < (int)bases->size(); ++i)
			if ((*bases)[i] == b) { p["tBaseId"] = i; break; }
	}
	else if (auto* c = dynamic_cast<Craft*>(target))
	{
		p["targetType"] = "xcraft";
		p["tBaseId"] = craftBaseIndex(game, c);
		p["tCraftId"] = c->getId();
		p["tCraftType"] = c->getRules()->getType();
	}
	else
	{
		p["targetType"] = "point"; // waypoint (or unknown) -> a lon/lat point
	}
}

// Launch when the craft is grounded, retarget when airborne (same handler; the
// name keeps the wire readable).
const char* orderCmdFor(const Craft* craft)
{
	return craft->getStatus() == "STR_OUT" ? "craft_retarget" : "craft_launch";
}

} // anonymous namespace

void submitCraftTarget(Game* game, Craft* craft, Target* target)
{
	if (!game || !craft || !target) return;
	Json::Value p;
	p["craftId"] = craft->getId();
	p["craftType"] = craft->getRules()->getType();
	describeTarget(game, target, p);
	submitLocalCmd(game, orderCmdFor(craft), craftBaseIndex(game, craft), p);
}

void submitCraftPoint(Game* game, Craft* craft, double lon, double lat)
{
	if (!game || !craft) return;
	Json::Value p;
	p["craftId"] = craft->getId();
	p["craftType"] = craft->getRules()->getType();
	p["targetType"] = "point";
	p["lon"] = lon;
	p["lat"] = lat;
	submitLocalCmd(game, orderCmdFor(craft), craftBaseIndex(game, craft), p);
}

void submitCraftReturn(Game* game, Craft* craft)
{
	if (!game || !craft) return;
	Json::Value p;
	p["craftId"] = craft->getId();
	p["craftType"] = craft->getRules()->getType();
	submitLocalCmd(game, "craft_return", craftBaseIndex(game, craft), p);
}

void submitCraftPatrol(Game* game, Craft* craft, bool autoPatrol)
{
	if (!game || !craft) return;
	Json::Value p;
	p["craftId"] = craft->getId();
	p["craftType"] = craft->getRules()->getType();
	p["auto"] = autoPatrol;
	submitLocalCmd(game, "craft_patrol", craftBaseIndex(game, craft), p);
}

int lastCraftOrderSeat(const Craft* craft)
{
	if (!craft) return -1;
	auto it = g_craftOrderSeat.find(craftKey(craft));
	return it == g_craftOrderSeat.end() ? -1 : it->second;
}

void submitCraftPilotAdd(Game* game, Craft* craft, int soldierId)
{
	if (!game || !craft) return;
	if (!game->getCoopMod() || !game->getCoopMod()->isSharedCampaign()) return;
	Json::Value p;
	p["craftId"] = craft->getId();
	p["craftType"] = craft->getRules()->getType();
	p["op"] = "add";
	p["soldierId"] = soldierId;
	submitLocalCmd(game, "craft_pilots", craftBaseIndex(game, craft), p);
}

bool removeOwnCraftPilots(Game* game, Craft* craft)
{
	if (!game || !craft) return false;
	if (!game->getCoopMod() || !game->getCoopMod()->isSharedCampaign()) return false;
	std::vector<Soldier*> list = craft->getPilotList(false, game->getMod());
	craft->removeAllPilots();
	for (auto* s : list)
		if (!ownsSoldier(game, s)) craft->addPilot(s->getId()); // the partner's picks stay
	Json::Value p;
	p["craftId"] = craft->getId();
	p["craftType"] = craft->getRules()->getType();
	p["op"] = "clear";
	submitLocalCmd(game, "craft_pilots", craftBaseIndex(game, craft), p);
	return true;
}

void submitCraftAssign(Game* game, Craft* craft, Soldier* soldier, bool onOff)
{
	if (!game || !craft || !soldier) return;
	Json::Value p;
	p["craftId"] = craft->getId();
	p["craftType"] = craft->getRules()->getType();
	p["soldierId"] = soldier->getId();
	p["soldierOwner"] = soldier->getOwnerPlayerId();
	p["onOff"] = onOff;
	submitLocalCmd(game, "craft_assign", craftBaseIndex(game, craft), p);
}

void submitCraftEquip(Game* game, Craft* craft, const std::string& itemType, int desiredOnCraft)
{
	if (!game || !craft) return;
	Json::Value p;
	p["craftId"] = craft->getId();
	p["craftType"] = craft->getRules()->getType();
	p["item"] = itemType;
	p["count"] = desiredOnCraft;
	submitLocalCmd(game, "craft_equip", craftBaseIndex(game, craft), p);
}

// see SharedEcon.h.
void craftVehiclesMoved(Game* game, Base* base, Craft* craft, const std::string& itemType, int before)
{
	if (!game || !base || !craft || base->_isForeignBase || !game->getSavedGame() || game->getSavedGame()->getMonthsPassed() == -1
		|| !game->getCoopMod() || !game->getCoopMod()->isSharedCampaign()) return;
	const RuleItem* item = game->getMod()->getItem(itemType, false);
	const int now = craft->getVehicleCount(itemType);
	if (item && item->getVehicleUnit() && now != before)
		submitCraftEquip(game, craft, itemType, now); // the absolute count; the host resolves it, the replica adopts (craftEquipVehicles)
}

void submitFacilityDisabled(Game* game, Base* base, int x, int y, bool disabled)
{
	if (!game || !base || base->_isForeignBase) return;
	if (!game->getCoopMod() || !game->getCoopMod()->isSharedCampaign()) return;
	Json::Value p;
	p["x"] = x;
	p["y"] = y;
	p["disabled"] = disabled;
	submitLocalCmd(game, "fac_disable", baseIndex(game, base), p);
}

void submitCraftWeaponDisabled(Game* game, Craft* craft, int slot)
{
	if (!game || !craft) return;
	if (!game->getCoopMod() || !game->getCoopMod()->isSharedCampaign()) return;
	if (slot < 0 || slot >= (int)craft->getWeapons()->size() || !craft->getWeapons()->at(slot)) return;
	Json::Value p;
	p["craftId"] = craft->getId();
	p["craftType"] = craft->getRules()->getType();
	p["slot"] = slot;
	p["disabled"] = craft->getWeapons()->at(slot)->isDisabled();
	submitLocalCmd(game, "craft_weapon_disable", craftBaseIndex(game, craft), p);
}

void submitCraftLoadout(Game* game, Craft* craft, const std::vector<std::string>& listed,
                        const ItemContainer& tmpl, bool onlyAdd)
{
	if (!game || !craft) return;
	Json::Value p;
	p["craftId"] = craft->getId();
	p["craftType"] = craft->getRules()->getType();
	p["onlyAdd"] = onlyAdd;
	Json::Value types(Json::arrayValue);
	for (const auto& type : listed) types.append(type);
	p["listed"] = types;
	Json::Value contents(Json::objectValue);
	for (const auto& entry : *tmpl.getContents())
		if (entry.first && entry.second > 0)
			contents[entry.first->getType()] = entry.second;
	p["template"] = contents;
	submitLocalCmd(game, "craft_loadout", craftBaseIndex(game, craft), p);
}

void submitCraftRearm(Game* game, Craft* craft, int slot, const std::string& weaponType)
{
	if (!game || !craft) return;
	Json::Value p;
	p["craftId"] = craft->getId();
	p["craftType"] = craft->getRules()->getType();
	p["slot"] = slot;
	p["weapon"] = weaponType;
	submitLocalCmd(game, "craft_rearm", craftBaseIndex(game, craft), p);
}

void submitSoldierArmor(Game* game, Base* base, Soldier* soldier, const std::string& armorType)
{
	if (!game || !base || !soldier) return;
	Json::Value p;
	p["soldierId"] = soldier->getId();
	p["armor"] = armorType;
	submitLocalCmd(game, "soldier_armor", baseIndex(game, base), p);
}

// see SharedEcon.h.
void baseEquipOpen(Game* game, Base* base)
{
	g_baseEquipMark = Json::Value(Json::nullValue);
	if (!game || !base || base->_isForeignBase || !game->getCoopMod() || !game->getCoopMod()->isSharedCampaign()) return;
	Json::Value m(Json::objectValue);
	m["base"] = baseIndex(game, base);
	m["soldiers"] = Json::Value(Json::objectValue);
	for (auto* s : *base->getSoldiers())
		m["soldiers"][std::to_string(s->getId())] = soldierEquipRecord(s);
	g_baseEquipMark = m;
	craftStageOpen(game, base); // the soldier screen's de-assign follows (the craft screen opened it before its staging)
}

void baseEquipOk(Game* game, Base* base)
{
	Json::Value mark = g_baseEquipMark;
	g_baseEquipMark = Json::Value(Json::nullValue);
	if (!game || !base || !mark.isObject() || mark.get("base", -1).asInt() != baseIndex(game, base)) return;
	if (!game->getCoopMod() || !game->getCoopMod()->isSharedCampaign()) return;
	Json::Value soldiers(Json::arrayValue);
	int restored = 0;
	for (auto* s : *base->getSoldiers())
	{
		const std::string key = std::to_string(s->getId());
		if (!mark["soldiers"].isMember(key)) continue; // arrived after the screen opened: not on it
		Json::Value now = soldierEquipRecord(s);
		if (now == mark["soldiers"][key]) continue;
		if (ownsSoldier(game, s))
			soldiers.append(now);
		else
		{
			soldierEquipAdopt(game, s, mark["soldiers"][key]); // the partner's gear stays the partner's
			++restored;
		}
	}
	Log(LOG_INFO) << "[SHARED] base equip OK: " << soldiers.size() << " own record(s) sent, " << restored
		<< " partner record(s) put back, base " << baseIndex(game, base);
	if (soldiers.empty()) return;
	Json::Value p(Json::objectValue);
	p["soldiers"] = soldiers;
	submitLocalCmd(game, "soldier_equip", baseIndex(game, base), p);
}

// see SharedEcon.h.
void submitLayoutTemplate(Game* game, Base* base, int index)
{
	if (!game || !base || base->_isForeignBase || !game->getSavedGame() || !game->getCoopMod() || !game->getCoopMod()->isSharedCampaign()) return;
	if (index < 0 || index >= SavedGame::MAX_EQUIPMENT_LAYOUT_TEMPLATES) return;
	SavedGame* sg = game->getSavedGame();
	Json::Value p(Json::objectValue);
	p["kind"] = "layout";
	p["index"] = index;
	p["layout"] = equipYaml(*sg->getGlobalEquipmentLayout(index));
	p["armor"] = sg->getGlobalEquipmentLayoutArmor(index);
	p["name"] = sg->getGlobalEquipmentLayoutName(index);
	submitLocalCmd(game, "equip_template", baseIndex(game, base), p);
}

void submitLoadoutTemplate(Game* game, Base* base, int index)
{
	if (!game || !base || base->_isForeignBase || !game->getSavedGame() || !game->getCoopMod() || !game->getCoopMod()->isSharedCampaign()) return;
	if (index < 0 || index >= SavedGame::MAX_CRAFT_LOADOUT_TEMPLATES) return;
	SavedGame* sg = game->getSavedGame();
	Json::Value p(Json::objectValue);
	p["kind"] = "loadout";
	p["index"] = index;
	p["items"] = Json::Value(Json::objectValue);
	for (const auto& pr : *sg->getGlobalCraftLoadout(index)->getContents())
		p["items"][pr.first->getType()] = pr.second;
	p["name"] = sg->getGlobalCraftLoadoutName(index);
	submitLocalCmd(game, "equip_template", baseIndex(game, base), p);
}

// see SharedEcon.h.
void craftDeploymentSaved(Game* game, const std::string& craftType)
{
	if (!game || !game->getSavedGame() || game->getSavedGame()->getMonthsPassed() == -1
		|| !game->getCoopMod() || !game->getCoopMod()->isSharedCampaign()) return;
	const auto& data = game->getSavedGame()->getCustomRuleCraftDeployments();
	const auto it = data.find(craftType);
	Json::Value p(Json::objectValue);
	p["craftType"] = craftType;
	p["saved"] = it != data.end();
	p["positions"] = Json::Value(Json::arrayValue);
	if (it != data.end())
		for (const auto& v : it->second)
		{
			Json::Value row(Json::arrayValue);
			for (int c : v) row.append(c);
			p["positions"].append(row);
		}
	submitLocalCmd(game, "craft_deployment", -1, p); // the end-state; the presser's own apply writes the same entry again
}

// See SharedEcon.h.
void baseArmorChanged(Game* game, Base* base, Soldier* soldier, const std::string& prevArmorType)
{
	if (!game || !base || !soldier || base->_isForeignBase || !game->getCoopMod() || !game->getCoopMod()->isSharedCampaign()) return;
	Armor* prev = game->getMod()->getArmor(prevArmorType, false);
	Armor* next = soldier->getArmor();
	if (!prev || !next || next == prev) return;
	if (ownsSoldier(game, soldier))
	{
		Json::Value p(Json::objectValue);
		p["soldierId"] = soldier->getId();
		p["armor"] = next->getType();
		p["tmpl"] = true; // soldierArmorApply: vanilla's template change leaves the last-selected armor
		submitLocalCmd(game, "soldier_armor", baseIndex(game, base), p);
		return;
	}
	// the partner's soldier: vanilla's change is put back at once - its armor store items, then its armor
	SavedGame* save = game->getSavedGame();
	if (save && save->getMonthsPassed() != -1)
	{
		if (next->getStoreItem()) base->getStorageItems()->addItem(next->getStoreItem());
		if (prev->getStoreItem()) base->getStorageItems()->removeItem(prev->getStoreItem());
	}
	soldier->setArmor(prev, true);
	Log(LOG_INFO) << "[SHARED] base armor change on the partner's soldier " << soldier->getId() << " put back, base " << baseIndex(game, base);
}

// see SharedEcon.h.
Json::Value craftItemsMark(Game* game, Base* base, Craft* craft)
{
	if (!game || !base || !craft || base->_isForeignBase || !game->getSavedGame() || game->getSavedGame()->getMonthsPassed() == -1
		|| !game->getCoopMod() || !game->getCoopMod()->isSharedCampaign()) return Json::Value(Json::nullValue);
	Json::Value m(Json::objectValue);
	for (const auto& pr : *craft->getItems()->getContents())
		if (pr.second > 0) m[pr.first->getType()] = pr.second;
	return m;
}

// See SharedEcon.h.
void craftItemsCommit(Game* game, Base* base, Craft* craft, const Json::Value& mark, bool every)
{
	if (!game || !base || !craft || !mark.isObject()) return;
	if (g_craftStage.isObject() && g_craftStage.get("base", -1).asInt() == baseIndex(game, base)) return; // the close commits
	const Json::Value now = craftItemsMark(game, base, craft);
	if (!now.isObject()) return;
	std::set<std::string> types;
	for (const auto& t : mark.getMemberNames()) types.insert(t);
	for (const auto& t : now.getMemberNames()) types.insert(t);
	std::vector<std::pair<std::string, int>> down, up; // decreases first: the host's capacity clamp (craftEquipApply) sees the room
	for (const auto& t : types)
	{
		const int before = mark.get(t, 0).asInt(), after = now.get(t, 0).asInt();
		const RuleItem* rule = game->getMod()->getItem(t, false);
		if ((after == before && !every) || !rule || rule->getVehicleUnit()) continue;
		(after < before ? down : up).emplace_back(t, after);
	}
	for (const auto& d : down) submitCraftEquip(game, craft, d.first, d.second);
	for (const auto& u : up) submitCraftEquip(game, craft, u.first, u.second);
	if (!down.empty() || !up.empty())
		Log(LOG_INFO) << "[SHARED] craft items commit: " << (down.size() + up.size()) << " type(s), craft " << craft->getId() << ", base " << baseIndex(game, base);
}

// see SharedEcon.h.
void craftStageOpen(Game* game, Base* base)
{
	if (!game || !base || base->_isForeignBase || !Options::oxceAlternateCraftEquipmentManagement || !game->getSavedGame()
		|| game->getSavedGame()->getMonthsPassed() == -1 || !game->getCoopMod() || !game->getCoopMod()->isSharedCampaign()) return;
	if (g_craftStage.isObject() && g_craftStage.get("base", -1).asInt() == baseIndex(game, base)) return; // the craft screen opened it
	Json::Value w(Json::objectValue);
	w["base"] = baseIndex(game, base);
	w["crafts"] = Json::Value(Json::arrayValue);
	for (auto* c : *base->getCrafts())
	{
		Json::Value rec(Json::objectValue);
		rec["craftId"] = c->getId();
		rec["craftType"] = c->getRules()->getType();
		rec["items"] = craftItemsMark(game, base, c);
		w["crafts"].append(rec);
	}
	w["seats"] = Json::Value(Json::objectValue);
	for (auto* s : *base->getSoldiers())
	{
		Json::Value seat(Json::nullValue);
		if (Craft* c = s->getCraft()) { seat = Json::Value(Json::objectValue); seat["craftId"] = c->getId(); seat["craftType"] = c->getRules()->getType(); }
		w["seats"][std::to_string(s->getId())] = seat;
	}
	g_craftStage = w;
	Log(LOG_INFO) << "[SHARED] craft staging window opened, base " << w["base"].asInt();
}

// see SharedEcon.h.
void craftStageClose(Game* game, Base* base)
{
	if (!game || !base || !g_craftStage.isObject() || g_craftStage.get("base", -1).asInt() != baseIndex(game, base)) return;
	Json::Value w = g_craftStage; // a copy: baseEquipOk's idiom
	g_craftStage = Json::Value(Json::nullValue); // closed first, so the commits below are not deferred
	std::set<Craft*> unseated;
	for (auto* s : *base->getSoldiers())
	{
		const std::string key = std::to_string(s->getId());
		if (s->getCraft() || !w["seats"].isMember(key) || !w["seats"][key].isObject()) continue;
		Craft* c = findCraft(base, w["seats"][key]["craftId"].asInt(), w["seats"][key]["craftType"].asString());
		if (!c) continue;
		submitCraftAssign(game, c, s, false); // vanilla's capacity outcome here is the shared seat (the partner's soldier too)
		unseated.insert(c);
	}
	for (const auto& rec : w["crafts"])
		if (Craft* c = findCraft(base, rec["craftId"].asInt(), rec["craftType"].asString()))
			craftItemsCommit(game, base, c, rec["items"], unseated.count(c) > 0); // a craft that lost a seat: every type
	Log(LOG_INFO) << "[SHARED] craft staging window closed, base " << w["base"].asInt() << ", " << unseated.size() << " craft(s) lost a seat";
}

// see SharedEcon.h. The rule travels by name; the host resolves the rest.
bool submitSoldierTransform(Game* game, Base* base, const std::string& rule, Soldier* soldier, const std::string& name)
{
	if (!game || !base || !soldier || !game->getCoopMod()) return false;
	if (game->getCoopMod()->isSharedCampaign())
	{
		if (base->_isForeignBase) return false;
	}
	else if (!game->getCoopMod()->isSeparateCampaign())
		return false;
	Json::Value p;
	p["rule"] = rule;
	p["soldierId"] = soldier->getId();
	p["dead"] = soldier->getDeath() != nullptr;
	p["name"] = name;
	submitLocalCmd(game, "soldier_transform", baseIndex(game, base), p);
	return true;
}

// see SharedEcon.h. The random-production window's right-click sale goes through the host's "sell" (re-priced there
// with the window's own formula; capped at the host's stores); nothing is written locally.
bool submitRandomProductionSale(Game* game, Base* base, const std::string& itemType, int qty)
{
	if (!game || !base || base->_isForeignBase) return false;
	if (!game->getCoopMod() || !game->getCoopMod()->isSharedCampaign()) return false;
	if (qty <= 0) return true; // nothing left to sell here; the window keeps vanilla's row bookkeeping
	Json::Value item(Json::objectValue), p(Json::objectValue);
	item["rule"] = itemType;
	item["qty"] = qty;
	p["items"] = Json::Value(Json::arrayValue);
	p["items"].append(item);
	p["capToStores"] = true;
	submitLocalCmd(game, "sell", baseIndex(game, base), p);
	return true;
}

// SHARED and a real base only (the SoldierInfoState rename guard); vanilla's
// local write already ran. The host resolves the value both worlds hold.
void submitSoldierRank(Game* game, Base* base, Soldier* soldier)
{
	if (!game || !base || !soldier || base->_isForeignBase) return;
	if (!game->getCoopMod() || !game->getCoopMod()->isSharedCampaign()) return;
	Json::Value p;
	p["soldierId"] = soldier->getId();
	p["rank"] = (int)soldier->getRank();
	submitLocalCmd(game, "soldier_rank", baseIndex(game, base), p);
}

void submitSoldierNationality(Game* game, Base* base, Soldier* soldier)
{
	if (!game || !base || !soldier || base->_isForeignBase) return;
	if (!game->getCoopMod() || !game->getCoopMod()->isSharedCampaign()) return;
	Json::Value p;
	p["soldierId"] = soldier->getId();
	p["nationality"] = soldier->getNationality();
	submitLocalCmd(game, "soldier_nationality", baseIndex(game, base), p);
}

void submitSoldierPsiTraining(Game* game, Base* base, Soldier* soldier)
{
	if (!game || !base || !soldier || base->_isForeignBase) return;
	if (!game->getCoopMod() || !game->getCoopMod()->isSharedCampaign()) return;
	Json::Value p;
	p["soldierId"] = soldier->getId();
	p["psi"] = soldier->isInPsiTraining();
	submitLocalCmd(game, "soldier_psi_training", baseIndex(game, base), p);
}

// the crew screen's two "remove soldiers" keys in SHARED - craft_assign off for every
// own soldier of @a base on a craft that is not OUT (only @a onlyCraft when non-null); true = handled.
bool submitCraftDeassign(Game* game, Base* base, Craft* onlyCraft)
{
	if (!game || !base || base->_isForeignBase) return false;
	if (!game->getCoopMod() || !game->getCoopMod()->isSharedCampaign()) return false;
	for (auto* s : *base->getSoldiers())
	{
		if (!ownsSoldier(game, s)) continue; // the hotkeys unseat only the local player's own soldiers
		Craft* sc = s->getCraft();
		if (!sc || sc->getStatus() == "STR_OUT") continue; // an OUT craft is locked (CraftSoldiersState :675-679, craftAssignValidate)
		if (onlyCraft && sc != onlyCraft) continue;
		submitCraftAssign(game, sc, s, false);
	}
	return true;
}

void submitSoldierTraining(Game* game, Base* base, bool psi,
	const std::vector<TrainingChange>& changes)
{
	if (!game || !base || changes.empty()) return;
	Json::Value soldiers(Json::arrayValue);
	for (const TrainingChange& change : changes)
	{
		Json::Value s;
		s["id"] = change.soldier->getId();
		s["training"] = change.training;
		if (!psi) s["queued"] = change.queued;
		soldiers.append(s);
	}
	Json::Value p;
	p["kind"] = psi ? "psi" : "martial";
	p["soldiers"] = soldiers;
	submitLocalCmd(game, "soldier_training", baseIndex(game, base), p);
}

void submitSoldierLayouts(Game* game, Base* base, const Json::Value& soldiers)
{
	if (!game || !base || !soldiers.isArray() || soldiers.empty()) return;
	Json::Value p;
	p["soldiers"] = soldiers;
	submitLocalCmd(game, "soldier_layout", baseIndex(game, base), p);
}

std::string serializeLayout(const std::vector<EquipmentLayoutItem*>& layout)
{
	YAML::YamlRootNodeWriter writer;
	writer.setAsMap();
	writer.write("layout", layout,
		[](YAML::YamlNodeWriter& w, EquipmentLayoutItem* i)
		{ i->save(w.write()); });
	return writer.emit().yaml;
}

std::vector<EquipmentLayoutItem*> deserializeLayout(Game* game, const std::string& text)
{
	std::vector<EquipmentLayoutItem*> out;
	if (!game || text.empty()) return out;
	YAML::YamlRootNodeReader reader(YAML::YamlString{text}, "soldierLayout");
	for (const auto& entry : reader["layout"].children())
	{
		try
		{
			out.push_back(new EquipmentLayoutItem(entry, game->getMod()));
		}
		catch (Exception&)
		{
			// an item this machine's mod does not know: skip it, as Soldier::load does
		}
	}
	return out;
}

void hostLandingPrompt(Game* game, Craft* craft, int seat, int shade)
{
	if (!sharedHost(game) || !craft) return;
	Json::Value p;
	p["craftId"] = craft->getId();
	p["craftType"] = craft->getRules()->getType();
	p["initiatorSeat"] = seat;
	p["shade"] = shade;
	Log(LOG_INFO) << "[SHARED] landing prompt brokered to seat " << seat
		<< " for " << craftKey(craft);
	submitLocalCmd(game, "land_prompt", craftBaseIndex(game, craft), p);
}

// patrol_prompt payload: { craftId, craftType }. Host-origin (simAccept; applier
// replica-only). A craft reached a plain patrol WAYPOINT. The host runs the only sim,
// so without this the alert + waypoint cleanup never reach the clients (the client's
// craft keeps a stale _dest -> the destination line and waypoint marker render forever,
// and no "reached destination" popup appears). Mirrors land_prompt, but patrol needs no
// host-authoritative resolver: OK is a local no-op and Redirect rides the craft_order lane.
void hostPatrolPrompt(Game* game, Craft* craft)
{
	if (!sharedHost(game) || !craft) return;
	Json::Value p;
	p["craftId"] = craft->getId();
	p["craftType"] = craft->getRules()->getType();
	submitLocalCmd(game, "patrol_prompt", craftBaseIndex(game, craft), p);
}

void hostBaseDamaged(Game* game, Base* base, const Ufo* ufo)
{
	if (!sharedHost(game) || !base) return;
	Json::Value p;
	p["ufoId"] = ufo ? ufo->getId() : -1;
	Json::Value facs(Json::arrayValue);
	for (const auto* f : *base->getFacilities())
	{
		Json::Value j;
		j["type"] = f->getRules()->getType();
		j["x"] = f->getX();
		j["y"] = f->getY();
		j["buildTime"] = f->getBuildTime();
		facs.append(j);
	}
	p["facilities"] = facs;
	submitLocalCmd(game, "base_damaged", baseIndex(game, base), p);
}

void hostAlienBaseFound(Game* game, AlienBase* alienBase)
{
	if (!sharedHost(game) || !alienBase) return;
	Json::Value p;
	p["alienBaseId"] = alienBase->getId();
	p["coopId"] = alienBase->_coop_alienbase_id;
	p["deployment"] = alienBase->getDeployment()->getType();
	p["startMonth"] = alienBase->getStartMonth();
	p["lon"] = alienBase->getLongitude();
	p["lat"] = alienBase->getLatitude();
	p["pactCountry"] = alienBase->getPactCountry();
	p["race"] = alienBase->getAlienRace();
	p["ownerPlayerName"] = alienBase->getOwnerPlayerName();
	submitLocalCmd(game, "alien_base_found", 0, p);
}

// ---- text nodes - the sender ships a key and its pieces, never its own language ----
Json::Value textKey(const std::string& key, std::initializer_list<Json::Value> args)
{
	Json::Value n(Json::objectValue);
	n["k"] = key;
	Json::Value a(Json::arrayValue);
	for (const auto& arg : args)
		a.append(arg);
	n["a"] = a;
	return n;
}

Json::Value textLiteral(const std::string& text)
{
	Json::Value n(Json::objectValue);
	n["t"] = text;
	return n;
}

Json::Value textName(Game* game, const Target* target)
{
	if (!target)
		return textLiteral("");
	Language* lang = game->getLanguage();
	const std::string shown = target->getName(lang);
	if (dynamic_cast<const Base*>(target) || shown != target->getDefaultName(lang))
		return textLiteral(shown); // a player-typed name reads the same in every language
	if (const Craft* craft = dynamic_cast<const Craft*>(target))
		return textKey("STR_CRAFTNAME", {textKey(craft->getType()), Json::Value(craft->getId())}); // Craft::getDefaultName
	return textKey(target->getMarkerName(), {Json::Value(target->getMarkerId())}); // Target / Ufo::getDefaultName
}

Json::Value craftStatusText(Game* game, const Craft* craft)
{
	// the branches of Craft::getGeoscapeStatusString (Craft.cpp :1107-:1146), same order
	if (craft->getLowFuel())
		return textKey("STR_LOW_FUEL_RETURNING_TO_BASE");
	if (craft->getMissionComplete())
		return textKey("STR_MISSION_COMPLETE_RETURNING_TO_BASE");
	const Target* dest = craft->getDestination();
	if (dest == nullptr)
		return textKey("STR_PATROLLING");
	if (dest == (const Target*)craft->getBase())
		return textKey("STR_RETURNING_TO_BASE");
	if (const Ufo* u = dynamic_cast<const Ufo*>(dest))
	{
		if (craft->isInDogfight())
			return textKey("STR_TAILING_UFO");
		if (u->getStatus() == Ufo::FLYING)
			return textKey("STR_INTERCEPTING_UFO", {Json::Value(u->getId())});
		return textKey("STR_DESTINATION_UC_", {textName(game, u)});
	}
	return textKey("STR_DESTINATION_UC_", {textName(game, dest)});
}

std::string textRender(Game* game, const Json::Value& node)
{
	if (!node.isObject())
		return "";
	if (node.isMember("t"))
		return node["t"].asString();
	LocalizedText text = game->getLanguage()->getString(node.get("k", "").asString());
	const Json::Value& args = node["a"];
	for (Json::ArrayIndex i = 0; args.isArray() && i < args.size(); ++i)
	{
		if (args[i].isIntegral())
			text = static_cast<const LocalizedText&>(text).arg(args[i].asInt());
		else
			text = static_cast<const LocalizedText&>(text).arg(textRender(game, args[i]));
	}
	return text;
}

void hostAlert(Game* game, const std::string& cls, const std::string& msg,
               Base* base, int craftId, const std::vector<std::string>& names,
               const std::vector<int>& ids, bool flag, const Json::Value& rows, const Json::Value& text)
{
	if (!sharedHost(game)) return;
	Json::Value p;
	p["cls"] = cls;
	p["msg"] = msg;
	p["craftId"] = craftId;
	p["flag"] = flag;
	Json::Value jn(Json::arrayValue);
	for (const auto& n : names) jn.append(n);
	p["names"] = jn;
	Json::Value ji(Json::arrayValue);
	for (int i : ids) ji.append(i);
	p["ids"] = ji;
	if (rows.isArray() && !rows.empty())
		p["rows"] = rows;
	if (text.isObject()) p["text"] = text; // the replica renders it instead of msg
	submitLocalCmd(game, "alert", base ? baseIndex(game, base) : 0, p);
}

void hostAlertText(Game* game, const std::string& cls, const Json::Value& text, Base* base, int craftId)
{
	hostAlert(game, cls, "", base, craftId, {}, {}, false, Json::Value(), text);
}

// ---- geo_event - the host side ------------------------------------------------------------
namespace {
Json::Value geoItemMap(const ItemContainer* ic)
{
	Json::Value m(Json::objectValue);
	for (const auto& kv : *ic->getContents()) m[kv.first->getType()] = kv.second;
	return m;
}
template <typename F> std::string geoYaml(F save)
{
	YAML::YamlRootNodeWriter writer;
	writer.setAsMap();
	save(writer["n"]);
	return writer.emit().yaml;
}
// Changed members of two flat objects: @a now's value for every key whose value differs from @a was.
Json::Value geoChanged(const Json::Value& was, const Json::Value& now)
{
	Json::Value out(Json::objectValue);
	for (const auto& k : now.getMemberNames())
		if (!was.isMember(k) || was[k] != now[k]) out[k] = now[k];
	return out;
}
}

Json::Value eventMark(Game* game)
{
	if (!sharedCampaignHost(game) || !game->getSavedGame() || game->getSavedGame()->getBases()->empty())
		return Json::Value(Json::nullValue);
	SavedGame* save = game->getSavedGame();
	Base* hq = save->getBases()->front();
	Json::Value m(Json::objectValue), stores(Json::arrayValue), projects(Json::arrayValue), craftItems(Json::objectValue),
		discovered(Json::arrayValue), status(Json::objectValue), regions(Json::objectValue), ids(Json::objectValue);
	m["transfers"] = (int)hq->getTransfers()->size();
	m["crafts"] = (int)hq->getCrafts()->size();
	for (size_t i = 0; i < save->getBases()->size(); ++i)
	{
		Base* b = (*save->getBases())[i];
		stores.append(geoItemMap(b->getStorageItems()));
		Json::Value names(Json::arrayValue);
		for (auto* rp : b->getResearch()) names.append(rp->getRules()->getName());
		projects.append(names);
		for (auto* c : *b->getCrafts())
		{
			Json::Value& j = craftItems[craftKey(c)];
			j["base"] = (int)i; j["craft"] = c->getRules()->getType(); j["id"] = c->getId(); j["items"] = geoItemMap(c->getItems());
		}
	}
	for (auto* r : save->getDiscoveredResearch()) discovered.append(r->getName());
	for (const auto& kv : save->getResearchRuleStatusRaw()) status[kv.first] = kv.second;
	for (auto* rg : *save->getRegions())
		regions[rg->getRules()->getType()] = rg->getActivityXcom().empty() ? 0 : rg->getActivityXcom().back();
	for (const auto& kv : save->getAllIds()) ids[kv.first] = kv.second;
	m["stores"] = stores; m["projects"] = projects; m["craftItems"] = craftItems; m["discovered"] = discovered;
	m["status"] = status; m["regions"] = regions; m["ids"] = ids;
	m["diary"] = (int)save->getResearchDiary().size();
	m["score"] = save->getResearchScores().empty() ? 0 : save->getResearchScores().back();
	return m;
}

void hostGeoEvent(Game* game, const RuleEvent& rule, const Json::Value& mark, State* eventState)
{
	auto* ev = dynamic_cast<GeoscapeEventState*>(eventState);
	if (mark.isNull() || !ev || !sharedCampaignHost(game)) return;
	SavedGame* save = game->getSavedGame();
	Mod* mod = game->getMod();
	Base* hq = save->getBases()->front();
	const Json::Value now = eventMark(game);
	Json::Value p(Json::objectValue), picks(Json::objectValue), rows(Json::arrayValue), transfers(Json::arrayValue),
		crafts(Json::arrayValue), store(Json::arrayValue), craftItems(Json::arrayValue), research(Json::objectValue),
		added(Json::arrayValue), removed(Json::arrayValue), diary(Json::arrayValue), projects(Json::arrayValue);
	p["event"] = rule.getName();
	// the window's picks, recorded by eventLogic where vanilla made them (ids only; the replica renders them)
	const CoopEventPicks pk = ev->coopPicks();
	for (const auto& r : pk.rows)
	{
		Json::Value a(Json::arrayValue);
		a.append(r.first);
		a.append(r.second);
		rows.append(a);
	}
	picks["region"] = pk.region; picks["city"] = pk.city; picks["rows"] = rows;
	picks["research"] = pk.research; picks["bonus"] = pk.bonus;
	p["picks"] = picks;
	// new hq transfers / crafts: eventLogic and its research side effects only append
	for (size_t i = mark["transfers"].asUInt(); i < hq->getTransfers()->size(); ++i)
	{
		Transfer* t = (*hq->getTransfers())[i];
		transfers.append(geoYaml([&](YAML::YamlNodeWriter w) { t->save(w, hq, mod); }));
	}
	for (size_t i = mark["crafts"].asUInt(); i < hq->getCrafts()->size(); ++i)
	{
		Craft* c = (*hq->getCrafts())[i];
		crafts.append(geoYaml([&](YAML::YamlNodeWriter w) { c->save(w, mod->getScriptGlobal()); }));
	}
	p["transfers"] = transfers; p["crafts"] = crafts;
	// changed stores (whole map per base) and changed items of crafts that existed before the event
	for (Json::ArrayIndex b = 0; b < now["stores"].size(); ++b)
	{
		if (b < mark["stores"].size() && mark["stores"][b] == now["stores"][b]) continue;
		Json::Value s(Json::objectValue);
		s["base"] = (int)b; s["items"] = now["stores"][b];
		store.append(s);
	}
	for (const auto& k : now["craftItems"].getMemberNames())
		if (mark["craftItems"].isMember(k) && mark["craftItems"][k]["items"] != now["craftItems"][k]["items"])
			craftItems.append(now["craftItems"][k]);
	p["store"] = store; p["craftItems"] = craftItems;
	// research: discovered added / removed (with the popped flag), changed statuses, new diary entries, changed projects
	std::set<std::string> before, after;
	for (const auto& n : mark["discovered"]) before.insert(n.asString());
	for (const auto& n : now["discovered"]) after.insert(n.asString());
	auto named = [&](const std::string& n)
	{
		Json::Value e(Json::objectValue);
		const RuleResearch* r = mod->getResearch(n, false);
		e["name"] = n;
		e["popped"] = r != nullptr && save->wasResearchPopped(r);
		return e;
	};
	for (const auto& n : after) if (!before.count(n)) added.append(named(n));
	for (const auto& n : before) if (!after.count(n)) removed.append(named(n));
	const auto& di = save->getResearchDiary();
	for (size_t i = mark["diary"].asUInt(); i < di.size(); ++i)
	{
		const ResearchDiaryEntry* e = di[i];
		diary.append(geoYaml([&](YAML::YamlNodeWriter w) { e->save(w); }));
	}
	for (Json::ArrayIndex b = 0; b < now["projects"].size(); ++b)
	{
		if (b < mark["projects"].size() && mark["projects"][b] == now["projects"][b]) continue;
		Json::Value pr(Json::objectValue);
		pr["base"] = (int)b; pr["names"] = now["projects"][b];
		projects.append(pr);
	}
	research["added"] = added; research["removed"] = removed; research["diary"] = diary; research["projects"] = projects;
	research["status"] = geoChanged(mark["status"], now["status"]);
	p["research"] = research;
	if (mark["score"] != now["score"]) p["score"] = now["score"];
	p["regions"] = geoChanged(mark["regions"], now["regions"]);
	p["ids"] = geoChanged(mark["ids"], now["ids"]);
	submitLocalCmd(game, "geo_event", 0, p);
}

namespace { // ---- research_grant - the host side ---------------------------------------------
std::vector<std::string> g_grantArticles; // host: the arc articles vanilla opened since the last research_grant
}
void noteGrantArticle(Game* game, const RuleResearch* research)
{
	if (!research || !sharedCampaignHost(game)) return;
	g_grantArticles.push_back(research->getLookup().empty() ? research->getName() : research->getLookup());
}
void hostResearchGrant(Game* game, const Json::Value& mark, const char* source, bool withScore)
{
	if (mark.isNull() || !sharedCampaignHost(game))
	{
		g_grantArticles.clear();
		return;
	}
	SavedGame* save = game->getSavedGame();
	Mod* mod = game->getMod();
	const Json::Value now = eventMark(game);
	Json::Value p(Json::objectValue), research(Json::objectValue), added(Json::arrayValue), removed(Json::arrayValue),
		diary(Json::arrayValue), projects(Json::arrayValue), articles(Json::arrayValue);
	std::set<std::string> before, after;
	for (const auto& n : mark["discovered"]) before.insert(n.asString());
	for (const auto& n : now["discovered"]) after.insert(n.asString());
	auto named = [&](const std::string& n)
	{
		Json::Value e(Json::objectValue);
		const RuleResearch* r = mod->getResearch(n, false);
		e["name"] = n;
		e["popped"] = r != nullptr && save->wasResearchPopped(r);
		return e;
	};
	for (const auto& n : after) if (!before.count(n)) added.append(named(n));
	for (const auto& n : before) if (!after.count(n)) removed.append(named(n));
	const auto& di = save->getResearchDiary();
	for (size_t i = mark["diary"].asUInt(); i < di.size(); ++i)
	{
		const ResearchDiaryEntry* e = di[i];
		diary.append(geoYaml([&](YAML::YamlNodeWriter w) { e->save(w); }));
	}
	for (Json::ArrayIndex b = 0; b < now["projects"].size(); ++b)
	{
		if (b < mark["projects"].size() && mark["projects"][b] == now["projects"][b]) continue;
		Json::Value pr(Json::objectValue);
		pr["base"] = (int)b; pr["names"] = now["projects"][b];
		projects.append(pr);
	}
	for (const auto& a : g_grantArticles) articles.append(a);
	g_grantArticles.clear();
	research["added"] = added; research["removed"] = removed; research["diary"] = diary; research["projects"] = projects;
	research["status"] = geoChanged(mark["status"], now["status"]);
	const Json::Value ids = geoChanged(mark["ids"], now["ids"]);
	const bool scoreChanged = withScore && mark["score"] != now["score"];
	if (added.empty() && removed.empty() && diary.empty() && projects.empty() && research["status"].empty() && ids.empty()
		&& !scoreChanged && articles.empty())
		return; // nothing granted (no arc fired; a deployment without despawn research or counters)
	p["source"] = source;
	p["research"] = research;
	if (scoreChanged) p["score"] = now["score"];
	p["ids"] = ids;
	p["articles"] = articles;
	submitLocalCmd(game, "research_grant", 0, p);
}

// ---- prod_fx - the host side --------------------------------------------------------------
Json::Value productionFxMark(Game* game, Base* base)
{
	if (!sharedCampaignHost(game) || !base || !game->getSavedGame()) return Json::Value(Json::nullValue);
	SavedGame* save = game->getSavedGame();
	Json::Value m(Json::objectValue), crafts(Json::objectValue), ids(Json::objectValue);
	m["stores"] = geoItemMap(base->getStorageItems());
	m["transfers"] = (int)base->getTransfers()->size();
	for (auto* c : *base->getCrafts())
	{
		Json::Value k(Json::objectValue);
		k["type"] = c->getRules()->getType(); k["id"] = c->getId();
		crafts[craftKey(c)] = k;
	}
	m["crafts"] = crafts;
	m["engineers"] = base->getEngineers();
	for (const auto& kv : save->getAllIds()) ids[kv.first] = kv.second;
	m["ids"] = ids;
	m["score"] = save->getResearchScores().empty() ? 0 : save->getResearchScores().back();
	m["funds"] = Json::Value::Int64(save->getFunds());
	return m;
}

void hostProductionFx(Game* game, Base* base, const std::string& manufacture, const Json::Value& mark)
{
	if (mark.isNull() || !sharedCampaignHost(game) || !base) return;
	Mod* mod = game->getMod();
	Production* prod = findProduction(base, manufacture);
	Json::Value p(Json::objectValue), transfers(Json::arrayValue), crafts(Json::arrayValue), removed(Json::arrayValue);
	p["manufacture"] = manufacture;
	for (size_t i = mark["transfers"].asUInt(); i < base->getTransfers()->size(); ++i) // Production::step only appends
	{
		Transfer* t = (*base->getTransfers())[i];
		if (Soldier* s = t->getSoldier())
			if (s->getOwnerPlayerId() == 999) s->setOwnerPlayerId(prod && prod->getCoopStarterSeat() >= 0 ? prod->getCoopStarterSeat() : s->getId() % 2); // the produced soldier's owner
		transfers.append(geoYaml([&](YAML::YamlNodeWriter w) { t->save(w, base, mod); }));
	}
	std::set<std::string> now;
	for (auto* c : *base->getCrafts())
	{
		now.insert(craftKey(c));
		if (!mark["crafts"].isMember(craftKey(c)))
			crafts.append(geoYaml([&](YAML::YamlNodeWriter w) { c->save(w, mod->getScriptGlobal()); }));
	}
	for (const auto& k : mark["crafts"].getMemberNames())
		if (!now.count(k)) removed.append(mark["crafts"][k]); // startItem's required crafts
	const Json::Value after = productionFxMark(game, base);
	if (mark["stores"] != after["stores"]) p["stores"] = after["stores"];
	if (mark["engineers"] != after["engineers"]) p["engineers"] = after["engineers"];
	if (prod) p["assigned"] = prod->getAssignedEngineers();
	p["ids"] = geoChanged(mark["ids"], after["ids"]);
	if (mark["score"] != after["score"]) p["score"] = after["score"];
	if (transfers.empty() && crafts.empty() && removed.empty() && !p.isMember("stores") && !p.isMember("engineers")
		&& p["ids"].empty() && !p.isMember("score") && mark["funds"] == after["funds"])
		return; // this hour changed nothing at the base (progress rides day_tick)
	p["transfers"] = transfers;
	p["crafts"] = crafts;
	p["craftsRemoved"] = removed;
	submitLocalCmd(game, "prod_fx", baseIndex(game, base), p);
}

void flushEventWindows(Game* game, GeoscapeState* gs)
{
	if (!game || connectionTCP::getHost() || g_eventWindows.empty()) return;
	std::vector<QueuedEventWindow> queued;
	queued.swap(g_eventWindows);
	Log(LOG_INFO) << "[SHARED] geo_event: " << queued.size() << " queued event window(s) shown on the returned geoscape";
	for (const auto& w : queued) showEventWindow(game, gs, *w.rule, w.picks);
}

int pendingEventWindows() { return (int)g_eventWindows.size(); }

void clearEventWindows()
{
	if (!g_eventWindows.empty())
		Log(LOG_INFO) << "[SHARED] geo_event: session teardown drops " << g_eventWindows.size() << " queued event window(s)";
	g_eventWindows.clear();
}

void submitLandReply(Game* game, Craft* craft, bool yes, bool patrol)
{
	if (!game || !craft) return;
	Json::Value p;
	p["craftId"] = craft->getId();
	p["craftType"] = craft->getRules()->getType();
	p["yes"] = yes;
	p["patrol"] = patrol;
	submitLocalCmd(game, "land_reply", craftBaseIndex(game, craft), p);
}

// land_close payload: { craftId, craftType }. Host -> all seats: the landing was
// resolved (any seat answered), so every remaining broker ConfirmLandingState closes
// itself (ConfirmLandingState::think consumes the resolved mark). Replica-only apply.
void broadcastLandClose(Game* game, Craft* craft)
{
	if (!sharedHost(game) || !craft) return;
	Json::Value p;
	p["craftId"] = craft->getId();
	p["craftType"] = craft->getRules()->getType();
	submitLocalCmd(game, "land_close", craftBaseIndex(game, craft), p);
}

bool ownsSoldier(Game* game, const Soldier* soldier)
{
	if (!game || !soldier) return false;
	connectionTCP* coop = game->getCoopMod();
	if (!coop || !(coop->isSharedCampaign() || coop->isSeparateCampaign()))
		return true; // solo: not owner-gated
	return soldier->getOwnerPlayerId() == connectionTCP::localSeat();
}

std::vector<Soldier*> visibleSoldiers(Game* game, Base* base)
{
	std::vector<Soldier*> out;
	if (!base) return out;
	connectionTCP* coop = game ? game->getCoopMod() : nullptr;
	bool playerOwnedRoster = coop
		&& (coop->isSharedCampaign() || coop->isSeparateCampaign());
	int seat = playerOwnedRoster ? connectionTCP::localSeat() : -1;
	for (auto* s : *base->getSoldiers())
	{
		if (!playerOwnedRoster || s->getOwnerPlayerId() == seat)
			out.push_back(s);
	}
	return out;
}

// The roster index behind display row @a row of an own-only list
// (AllocateTrainingState / AllocatePsiTrainingState); identity outside SHARED.
size_t visibleRowToRosterIndex(Game* game, Base* base, size_t row)
{
	if (!base) return row;
	std::vector<Soldier*> view = visibleSoldiers(game, base);
	if (row >= view.size()) return row;
	const auto& all = *base->getSoldiers();
	for (size_t i = 0; i < all.size(); ++i)
		if (all[i] == view[row]) return i;
	return row;
}

bool submitSoldierMove(Game* game, Base* base, const std::vector<Soldier*>& visible,
	unsigned int row, bool up, bool max)
{
	if (!game || !base || row >= visible.size()) return false;
	if (up ? row == 0 : row + 1 >= visible.size()) return false;
	std::vector<Soldier*> order = visible;
	Soldier* moved = order[row];
	order.erase(order.begin() + row);
	const size_t to = max ? (up ? 0 : order.size()) : (up ? row - 1 : row + 1);
	order.insert(order.begin() + to, moved);
	submitSoldierOrder(game, base, order);
	return true;
}

void submitSoldierOrder(Game* game, Base* base, const std::vector<Soldier*>& order)
{
	if (!game || !base) return;
	Json::Value ids(Json::arrayValue);
	for (const Soldier* s : order) ids.append(s->getId());
	Json::Value p;
	p["order"] = ids;
	submitLocalCmd(game, "soldier_order", baseIndex(game, base), p);
}

void hostPlayerNotice(Game* game, const std::string& playerName, const std::string& msg)
{
	if (!sharedHost(game)) return;
	Json::Value p;
	p["cls"] = "CraftErrorState";
	p["msg"] = msg;
	p["player"] = playerName;
	submitLocalCmd(game, "alert", 0, p);
}

void hostSoldierStepBegin(Game* game, bool keepArmed)
{
	SavedGame* save = sharedHost(game) ? game->getSavedGame() : nullptr;
	if (!save)
	{
		g_soldierStepBefore.clear();
		g_soldierStepArmed = false;
		return;
	}
	// time1Month arms the snapshot and falls through into time1Day, whose own
	// call must keep it so the month's psi training is carried too.
	if (keepArmed && g_soldierStepArmed && g_soldierStepSave == save) return;
	g_soldierStepBefore.clear();
	for (auto* base : *save->getBases())
		for (auto* soldier : *base->getSoldiers())
			g_soldierStepBefore[soldier] = soldierStepState(soldier);
	g_soldierStepSave = save;
	g_soldierStepArmed = true;
}

void hostDayTick(Game* game)
{
	if (!sharedHost(game)) return;
	SavedGame* save = game->getSavedGame();
	if (!save) return;
	// Only a snapshot of this world, taken before this step, can say what the
	// step changed.
	const bool armed = g_soldierStepArmed && g_soldierStepSave == save;
	auto* bases = save->getBases();
	for (int bi = 0; bi < (int)bases->size(); ++bi)
	{
		Base* base = (*bases)[bi];
		Json::Value soldiers(Json::arrayValue);
		if (armed)
			for (auto* soldier : *base->getSoldiers())
			{
				auto hit = g_soldierStepBefore.find(soldier);
				if (hit == g_soldierStepBefore.end()) continue; // new this step: carried by its own result
				const SoldierStepState now = soldierStepState(soldier);
				if (!sameStepState(hit->second, now))
					soldiers.append(soldierStepJson(now));
			}
		// carry each running production's _timeSpent and each research
		// project's _spent so the frozen replica's progress columns stay current
		// (its own step() never runs). Small payload; sent whole each active day.
		Json::Value productions(Json::arrayValue);
		for (auto* prod : base->getProductions())
		{
			Json::Value jp;
			jp["item"] = prod->getRules()->getName();
			jp["spent"] = prod->getTimeSpent();
			productions.append(jp);
		}
		Json::Value research(Json::arrayValue);
		for (auto* rp : base->getResearch())
		{
			Json::Value jr;
			jr["project"] = rp->getRules()->getName();
			jr["spent"] = rp->getSpent();
			research.append(jr);
		}
		if (!soldiers.empty() || !productions.empty() || !research.empty())
		{
			Json::Value p;
			p["soldiers"] = soldiers;
			p["productions"] = productions;
			p["research"] = research;
			submitLocalCmd(game, "day_tick", bi, p);
		}
	}
	g_soldierStepBefore.clear();
	g_soldierStepArmed = false;
}

Json::Value soldierFxMark(Game* game)
{
	if (!sharedCampaignHost(game) || !game->getSavedGame()) return Json::Value(Json::nullValue);
	Json::Value m(Json::objectValue);
	for (auto* base : *game->getSavedGame()->getBases())
		for (auto* s : *base->getSoldiers())
			m[std::to_string(s->getId())] = soldierFxRecord(s);
	return m;
}

void hostSoldierFx(Game* game, const Json::Value& mark)
{
	if (mark.isNull() || !sharedCampaignHost(game) || !game->getSavedGame()) return;
	auto* bases = game->getSavedGame()->getBases();
	for (int bi = 0; bi < (int)bases->size(); ++bi)
	{
		Json::Value soldiers(Json::arrayValue);
		for (auto* s : *(*bases)[bi]->getSoldiers())
		{
			const std::string key = std::to_string(s->getId());
			if (!mark.isMember(key)) continue; // not in the mark (arrived since): no training / recovery change to send
			Json::Value r = soldierFxRecord(s);
			if (r != mark[key]) soldiers.append(r);
		}
		if (!soldiers.empty())
		{
			Json::Value p(Json::objectValue);
			p["soldiers"] = soldiers;
			submitLocalCmd(game, "soldier_fx", bi, p);
		}
	}
}

// ---- craft_lost ----------------------------------------------------------------------------
Json::Value craftLostMark(Game* game, Base* base, Craft* craft)
{
	if (!sharedCampaignHost(game) || !base || !craft || !game->getSavedGame()) return Json::Value(Json::nullValue);
	Json::Value m(Json::objectValue), crew(Json::arrayValue);
	for (auto* s : *base->getSoldiers())
		if (s->getCraft() == craft) crew.append(s->getId());
	m["crew"] = crew;
	m["transfers"] = (int)base->getTransfers()->size();
	return m;
}

void hostCraftLost(Game* game, Base* base, Craft* craft, const Json::Value& mark)
{
	if (mark.isNull() || !sharedCampaignHost(game) || !base || !craft) return;
	SavedGame* save = game->getSavedGame();
	Json::Value p(Json::objectValue), evacuated(Json::arrayValue), killed(Json::arrayValue);
	p["craftId"] = craft->getId();
	p["craftType"] = craft->getRules()->getType();
	for (size_t i = mark["transfers"].asUInt(); i < base->getTransfers()->size(); ++i) // evacuateCrew only appends
		if (Soldier* s = (*base->getTransfers())[i]->getSoldier())
		{
			Json::Value e(Json::objectValue);
			e["id"] = s->getId();
			e["hours"] = (*base->getTransfers())[i]->getHours();
			e["training"] = s->isInTraining();
			e["rtwh"] = s->getReturnToTrainingWhenHealed();
			evacuated.append(e);
		}
	for (const auto& id : mark["crew"])
		for (auto* d : *save->getDeadSoldiers())
			if (d->getId() == id.asInt()) { killed.append(id.asInt()); break; }
	p["evacuated"] = evacuated;
	p["killed"] = killed;
	submitLocalCmd(game, "craft_lost", baseIndex(game, base), p);
}

void flushLostCrafts(Game* game, GeoscapeState* gs)
{
	if (!game || !gs || connectionTCP::getHost() || g_lostCrafts.empty()) return;
	SavedGame* save = game->getSavedGame();
	if (!save) { g_lostCrafts.clear(); return; }
	std::vector<std::pair<int, Json::Value> > keep;
	for (auto& e : g_lostCrafts)
	{
		Base* base = resolveBase(game, e.first);
		const Json::Value& p = e.second;
		Craft* craft = base ? findCraft(base, p.get("craftId", -1).asInt(), p.get("craftType", "").asString()) : nullptr;
		bool held = false;
		for (auto* df : gs->getDogfights())
			if (craft && df->getCraft() == craft) held = true;
		if (held) { keep.push_back(e); continue; } // its window closes first (df_open membership)
		int moved = 0, killedN = 0;
		if (base)
		{
			auto& roster = *base->getSoldiers();
			for (const auto& ev : p["evacuated"])
				for (auto it = roster.begin(); it != roster.end(); ++it)
					if ((*it)->getId() == ev.get("id", -1).asInt())
					{
						Soldier* s = *it;
						s->setCraft(0);
						s->setTraining(ev.get("training", false).asBool());
						s->setReturnToTrainingWhenHealed(ev.get("rtwh", s->getReturnToTrainingWhenHealed()).asBool());
						roster.erase(it);
						Transfer* t = new Transfer(ev.get("hours", 1).asInt());
						t->setSoldier(s);
						base->getTransfers()->push_back(t);
						++moved;
						break;
					}
			for (const auto& kv : p["killed"])
				if (Soldier* s = findSoldier(base, kv.asInt())) { save->killSoldier(true, s); ++killedN; }
		}
		if (craft)
		{
			save->stopHuntingXcomCraft(craft);
			base->removeCraft(craft, false);
			delete craft;
		}
		Log(LOG_INFO) << "[SHARED] craft_lost: " << p.get("craftType", "").asString() << " " << p.get("craftId", -1).asInt()
			<< (craft ? " removed" : " not found") << ", " << moved << " evacuated, " << killedN << " killed, base " << e.first;
	}
	g_lostCrafts.swap(keep);
}

// ---- PRD-J04 detect + PRD-J10 repair: world checksum -------------------------
const int RESYNC_COOLDOWN_MINUTES = 60; // one game hour between auto-resyncs
const int RESYNC_DEBOUNCE_MS = 3000;    // a mismatch must survive this to count
// A resync request whose stream shows no progress (no mark, no chunk) for this
// long was dropped by the host or died with the stream; the replica asks again.
// A result hold whose world is not adopted in this long is released (see
// releaseHeldResults).
const int RESYNC_PENDING_TIMEOUT_MS = 30000;

namespace {
// Wall-clock (not game-time) milliseconds: the debounce below measures how long a
// mismatch has SURVIVED, and a paused/slow geoscape must not stretch it.
int64_t steadyMs()
{
	using namespace std::chrono;
	return duration_cast<milliseconds>(steady_clock::now().time_since_epoch()).count();
}

// A monotone game-minute stamp for the throttle. GameTime has no epoch accessor,
// so compose one from its fields; months are 1-12 and days 1-31, so the ladder is
// strictly increasing even though it skips (nonexistent) day 30/31 of February.
// Only DIFFERENCES matter here, and only against a 60-minute window.
int64_t gameMinutes(SavedGame* save)
{
	if (!save || !save->getTime()) return -1;
	GameTime* t = save->getTime();
	int64_t days = ((int64_t)t->getYear() * 12 + t->getMonth()) * 31 + t->getDay();
	return days * 24 * 60 + t->getHour() * 60 + t->getMinute();
}

// GAP-4: the widened checksum's cheap O(bases) integer aggregates. Computed the
// SAME way on host (stamp) and replica (verify) so they are identical BY
// CONSTRUCTION - both walk the one replicated world - and only real store /
// roster / transfer / production drift moves them. Counts only: no per-item
// hashing and no string building, because this rides the ~2 kHz `time` heartbeat
// (session-notes-10 #1). Deliberately NOT the income/expenditure series: GAP-9
// made those host-authoritative (the shared_apply carries them, the replica adopts
// them verbatim), so they are now equal AT REST - but they still take a discrete
// jump at the monthly roll that host and replica apply a few ticks apart (the same
// transient funds has, only funds already gates the checksum). Adding them would
// double the false-positive surface for that roll transient without catching any
// desync funds/counts don't already catch, so they stay out (GAP-9 decision).
void worldAggregates(SavedGame* save, int64_t& items, int64_t& soldiers,
	int64_t& transfers, int64_t& productions)
{
	items = soldiers = transfers = productions = 0;
	if (!save) return;
	for (Base* base : *save->getBases())
	{
		items += base->getStorageItems()->getTotalQuantity();
		soldiers += (int64_t)base->getSoldiers()->size();
		transfers += (int64_t)base->getTransfers()->size();
		productions += (int64_t)base->getProductions().size();
	}
}

// Content terms of the world checksum. Each is an order-free sum of one hash
// per entry, so a container's iteration order (ItemContainer is keyed by rule
// POINTER, which differs per machine) never matters. Masked to 63 bits so the
// value travels as a non-negative Json Int64.
uint64_t chkMix(uint64_t x)
{
	x += 0x9E3779B97F4A7C15ULL;
	x = (x ^ (x >> 30)) * 0xBF58476D1CE4E5B9ULL;
	x = (x ^ (x >> 27)) * 0x94D049BB133111EBULL;
	return x ^ (x >> 31);
}

uint64_t chkEntry(const std::string& name, int64_t a, int64_t b)
{
	uint64_t h = 1469598103934665603ULL; // FNV-1a
	for (unsigned char c : name) { h ^= c; h *= 1099511628211ULL; }
	h = chkMix(h ^ ((uint64_t)a * 0x9E3779B97F4A7C15ULL));
	return chkMix(h ^ ((uint64_t)b * 0xC2B2AE3D27D4EB4FULL));
}

int64_t chkValue(uint64_t sum) { return (int64_t)(sum & 0x7FFFFFFFFFFFFFFFULL); }

// Every custom counter a rule can write (research increase/decreaseCounter and
// the eight deployment counters). The id map also holds object ids (craft, UFO,
// site numbers) that a replica does not mint, so only these names are compared.
const std::vector<std::string>& customCounterNames(const Mod* mod)
{
	static const Mod* cachedMod = nullptr;
	static std::vector<std::string> names;
	if (mod == cachedMod) return names;
	cachedMod = mod;
	names.clear();
	if (!mod) return names;
	auto add = [](const std::string& name) { if (!name.empty()) names.push_back(name); };
	for (const auto& entry : mod->getResearchMap())
		if (entry.second)
		{
			for (const auto& name : entry.second->getIncreaseCounter()) add(name);
			for (const auto& name : entry.second->getDecreaseCounter()) add(name);
		}
	for (const auto& type : mod->getDeploymentsList())
		if (const AlienDeployment* d = mod->getDeployment(type, false))
		{
			add(d->getCounterSuccess()); add(d->getCounterFailure());
			add(d->getCounterDespawn()); add(d->getCounterAll());
			add(d->getDecreaseCounterSuccess()); add(d->getDecreaseCounterFailure());
			add(d->getDecreaseCounterDespawn()); add(d->getDecreaseCounterAll());
		}
	std::sort(names.begin(), names.end());
	names.erase(std::unique(names.begin(), names.end()), names.end());
	return names;
}

int64_t chkCounters(SavedGame* save, const Mod* mod)
{
	uint64_t sum = 0;
	const auto& ids = save->getAllIds();
	for (const auto& name : customCounterNames(mod))
	{
		auto it = ids.find(name);
		if (it != ids.end()) sum += chkEntry(name, it->second, 0);
	}
	return chkValue(sum);
}

// Pending geoscape events by name, owner and the Separate shared flag. Not the
// countdown: a replica never counts down, so it holds the host's value at the
// last world_extras result.
int64_t chkEvents(SavedGame* save)
{
	uint64_t sum = 0;
	for (const GeoscapeEvent* ge : save->getGeoscapeEvents())
		if (!ge->isOver())
			sum += chkEntry(ge->getRules().getName() + '\x1f' + ge->getOwnerPlayerName(),
				ge->isCoopShared() ? 1 : 0, 0);
	return chkValue(sum);
}

int64_t chkProjects(SavedGame* save)
{
	uint64_t sum = 0;
	const auto& bases = *save->getBases();
	for (size_t i = 0; i < bases.size(); ++i)
		for (const ResearchProject* proj : bases[i]->getResearch())
			sum += chkEntry(proj->getRules()->getName(), (int64_t)i, 0);
	return chkValue(sum);
}

// Every base's stores by item type and quantity. This walks every stored item
// type, so it is recomputed at most every CHK_STORES_MS of real time; the stale
// value is far inside the RESYNC_DEBOUNCE_MS a mismatch must survive.
const int64_t CHK_STORES_MS = 250;

int64_t chkStores(SavedGame* save)
{
	static const SavedGame* cachedSave = nullptr;
	static int64_t cachedAt = -1;
	static int64_t cached = 0;
	const int64_t now = steadyMs();
	if (save == cachedSave && cachedAt >= 0 && now - cachedAt < CHK_STORES_MS) return cached;
	uint64_t sum = 0;
	const auto& bases = *save->getBases();
	for (size_t i = 0; i < bases.size(); ++i)
		for (const auto& item : *bases[i]->getStorageItems()->getContents())
			if (item.second != 0)
				sum += chkEntry(item.first->getType(), (int64_t)i, item.second);
	cachedSave = save;
	cachedAt = now;
	cached = chkValue(sum);
	return cached;
}

// Every base soldier's current stats, keyed by soldier id. The host alone trains
// soldiers (martial and psi training) and no result carries their stats, so a
// replica's soldiers can drift with every count equal. Walks every soldier, so it
// is cached like chkStores.
int64_t chkSoldierStats(SavedGame* save)
{
	static const SavedGame* cachedSave = nullptr;
	static int64_t cachedAt = -1;
	static int64_t cached = 0;
	const int64_t now = steadyMs();
	if (save == cachedSave && cachedAt >= 0 && now - cachedAt < CHK_STORES_MS) return cached;
	uint64_t sum = 0;
	for (Base* base : *save->getBases())
		for (const Soldier* soldier : *base->getSoldiers())
		{
			const UnitStats* stats = soldier->getCurrentStats();
			uint64_t h = chkMix((uint64_t)(int64_t)soldier->getId());
			UnitStats::fieldLoop([&](UnitStats::Ptr field)
			{
				h = chkMix(h ^ (uint64_t)(uint16_t)(stats->*field));
			});
			sum += h;
		}
	cachedSave = save;
	cachedAt = now;
	cached = chkValue(sum);
	return cached;
}

// Separate's one world keeps each player's wallet and private research in that
// player's profile. getFunds() reads the LOCAL player's wallet, which differs by
// machine, so the Separate checksum stamps every profile instead: one wallet and
// one completed-research count per player name, plus the sum of the wallets as
// the machine-independent chkFunds. Stamp and verify both call this.
bool separateChecksumTerms(SavedGame* save, Json::Value& funds, Json::Value& research,
	int64_t& totalFunds)
{
	funds = Json::Value(Json::objectValue);
	research = Json::Value(Json::objectValue);
	totalFunds = 0;
	if (!save || !save->isSeparateCoopCampaign()) return false;
	for (const auto& player : save->getSeparateCampaign().getPlayers())
	{
		const int64_t wallet = player.second.funds.empty() ? 0 : player.second.funds.back();
		funds[player.first] = Json::Value::Int64(wallet);
		research[player.first] = (int)player.second.completedResearch.size();
		totalFunds += wallet;
	}
	return true;
}

// Name-keyed integer maps compared by value (a parsed and a locally built
// Json::Value may differ in integer type).
bool sameNamedTerms(const Json::Value& a, const Json::Value& b)
{
	if (!a.isObject() || !b.isObject() || a.size() != b.size()) return false;
	for (const std::string& name : a.getMemberNames())
		if (!b.isMember(name) || a[name].asInt64() != b[name].asInt64()) return false;
	return true;
}

std::string namedTermsText(const Json::Value& terms)
{
	std::ostringstream ss;
	ss << "{";
	bool first = true;
	if (terms.isObject())
		for (const std::string& name : terms.getMemberNames())
		{
			ss << (first ? "" : ", ") << name << "=" << terms[name].asInt64();
			first = false;
		}
	ss << "}";
	return ss.str();
}
} // namespace

void attachWorldChecksum(Game* game, Json::Value& msg)
{
	if (!game || !game->getSavedGame()) return;
	SavedGame* save = game->getSavedGame();
	Json::Value playerFunds, playerResearch;
	int64_t totalFunds = 0;
	const bool separate = separateChecksumTerms(save, playerFunds, playerResearch, totalFunds);
	msg["chkFunds"] = Json::Value::Int64(separate ? totalFunds : save->getFunds());
	msg["chkBases"] = (int)save->getBases()->size();
	msg["chkResearch"] = (int)save->getDiscoveredResearch().size();
	if (separate)
	{
		// Separate: every player's wallet and private research count, by name.
		msg["chkPlayerFunds"] = playerFunds;
		msg["chkPlayerResearch"] = playerResearch;
	}

	// GAP-4: widen past funds/bases/research so store, roster, transfer and
	// production drift can no longer hide from the auto-repair (funds is the only
	// exact-VALUE field; the four below are counts). Stamp and compare MUST stay
	// in lock-step - both go through worldAggregates().
	int64_t items, soldiers, transfers, productions;
	worldAggregates(save, items, soldiers, transfers, productions);
	msg["chkItems"] = Json::Value::Int64(items);
	msg["chkSoldiers"] = Json::Value::Int64(soldiers);
	msg["chkTransfers"] = Json::Value::Int64(transfers);
	msg["chkProduction"] = Json::Value::Int64(productions);
	// issue #78: an orphaned replica mission site (a despawn the snapshot missed)
	// must trip the auto-repair too. Count only - the restream is the repair.
	msg["chkSites"] = (int)save->getMissionSites()->size();
	// Content terms: drift that keeps every count equal (a swapped store item, a
	// project only one machine runs, a custom counter, a pending event).
	msg["chkStores"] = Json::Value::Int64(chkStores(save));
	msg["chkProjects"] = Json::Value::Int64(chkProjects(save));
	msg["chkCounters"] = Json::Value::Int64(chkCounters(save, game->getMod()));
	msg["chkEvents"] = Json::Value::Int64(chkEvents(save));
	msg["chkSoldierStats"] = Json::Value::Int64(chkSoldierStats(save));
}

bool requestResync(Game* game, const std::string& why, bool force)
{
	if (!game || !game->getCoopMod() || !game->getCoopMod()->isSharedReplica()) return false;
	if (!force && g_resyncPending) return false;

	g_resyncPending = true;
	g_lastResyncGameMin = gameMinutes(game->getSavedGame());
	g_streamProgressMs = steadyMs();
	++g_resyncReqN;
	Log(LOG_WARNING) << "[SHARED] requesting a world resync from the host (" << why
		<< (force ? ", forced)" : ")");

	Json::Value req;
	// Separate keeps its own wire namespace (SeparateEcon.h).
	req["state"] = game->getCoopMod()->isSeparateCampaign()
		? "separate_resync_request" : "shared_resync_request";
	game->getCoopMod()->sendTCPPacketData(req.toStyledString());
	return true;
}

void notifyWorldAdopted()
{
	// A fresh authoritative world just landed: the repair took, so re-arm both the
	// in-flight guard and the "give up" latch. The cooldown stamp stays, so a
	// mismatch that reappears within the window is still treated as unrepairable.
	g_resyncPending = false;
	g_resyncGaveUp = false;
	g_applyHold = false; // the held shared applies drain onto the adopted world
	g_craftStage = Json::Value(Json::nullValue); // an adopted world ends any open staging window
	if (g_restreamMarks > 0)
	{
		// This world is a restream snapshot. Results still queued from before its
		// mark are already in it, so they must not apply again. The results after
		// the mark wait in g_heldResults and apply on the next update, to this world.
		{
			std::lock_guard<std::mutex> lk(g_mx);
			g_applyQ.clear();
		}
		if (--g_restreamMarks == 0) g_releaseHeld = true;
	}
}

void setApplyHold(bool on)
{
	g_applyHold = on;
}

void verifyWorldChecksum(Game* game, const Json::Value& msg)
{
	// Both single-world campaigns repair here. Separate's wallets are views of
	// the local player, so its funds and research terms are every player's
	// profile (separateChecksumTerms), never this machine's own wallet. PvP keeps
	// two worlds and is not a replica.
	if (!game || !game->getSavedGame() || !game->getCoopMod()
		|| !game->getCoopMod()->isSharedReplica()) return;
	if (!msg.isMember("chkFunds")) return; // older/non-single-world host
	if (g_craftStage.isObject()) { g_mismatchSinceMs = -1; return; } // this machine's own option-ON staging moves its stores until the screen closes
	SavedGame* save = game->getSavedGame();
	int64_t hostFunds = msg["chkFunds"].asInt64();
	int hostBases = msg.get("chkBases", -1).asInt();
	int hostResearch = msg.get("chkResearch", -1).asInt();
	// GAP-4 fields. -1 default => a host that predates this change did not stamp
	// them; since every real aggregate is >= 0, a negative host value can ONLY
	// mean "not sent" and must read as agreement, never a cross-version false
	// positive. Absent-or-equal, folded into the condition below.
	int64_t hostItems = msg.get("chkItems", -1).asInt64();
	int64_t hostSoldiers = msg.get("chkSoldiers", -1).asInt64();
	int64_t hostTransfers = msg.get("chkTransfers", -1).asInt64();
	int64_t hostProductions = msg.get("chkProduction", -1).asInt64();
	int hostSites = msg.get("chkSites", -1).asInt(); // issue #78; -1 = old host
	Json::Value myPlayerFunds, myPlayerResearch;
	int64_t myTotalFunds = 0;
	const bool separate = separateChecksumTerms(save, myPlayerFunds, myPlayerResearch,
		myTotalFunds);
	int64_t myFunds = separate ? myTotalFunds : save->getFunds();
	int myBases = (int)save->getBases()->size();
	int myResearch = (int)save->getDiscoveredResearch().size();
	int mySites = (int)save->getMissionSites()->size();
	int64_t myItems, mySoldiers, myTransfers, myProductions;
	worldAggregates(save, myItems, mySoldiers, myTransfers, myProductions);
	// Separate per-player terms; absent from a host that predates them.
	const Json::Value& hostPlayerFunds = msg["chkPlayerFunds"];
	const Json::Value& hostPlayerResearch = msg["chkPlayerResearch"];
	const bool playersAgree = !separate
		|| ((hostPlayerFunds.isNull() || sameNamedTerms(hostPlayerFunds, myPlayerFunds))
			&& (hostPlayerResearch.isNull()
				|| sameNamedTerms(hostPlayerResearch, myPlayerResearch)));
	// Content terms; absent from a host that predates them (agreement).
	const int64_t myStores = chkStores(save), myProjects = chkProjects(save);
	const int64_t myCounters = chkCounters(save, game->getMod()), myEvents = chkEvents(save);
	const int64_t mySoldierStats = chkSoldierStats(save);
	auto contentAgrees = [&msg](const char* key, int64_t mine)
	{
		return !msg.isMember(key) || msg[key].asInt64() == mine;
	};
	const bool contentAgree = contentAgrees("chkStores", myStores)
		&& contentAgrees("chkProjects", myProjects)
		&& contentAgrees("chkCounters", myCounters)
		&& contentAgrees("chkEvents", myEvents)
		&& contentAgrees("chkSoldierStats", mySoldierStats);
	if (hostFunds == myFunds && hostBases == myBases && hostResearch == myResearch
		&& playersAgree && contentAgree
		&& (hostItems < 0 || hostItems == myItems)
		&& (hostSoldiers < 0 || hostSoldiers == mySoldiers)
		&& (hostTransfers < 0 || hostTransfers == myTransfers)
		&& (hostProductions < 0 || hostProductions == myProductions)
		&& (hostSites < 0 || hostSites == mySites))
	{
		// Back in agreement: whatever drifted is gone. Re-arm the repair so a later,
		// unrelated drift gets its own auto-resync instead of the give-up popup.
		if (g_mismatchLogged)
		{
			Log(LOG_INFO) << "[SHARED] world checksum back in agreement with the host";
			g_mismatchLogged = false;
		}
		g_mismatchSinceMs = -1;
		g_resyncGaveUp = false;
		g_lastResyncGameMin = -1;
		return;
	}

	++g_mismatchN;

	// DEBOUNCE. A single mismatching heartbeat does NOT mean the world diverged:
	// the checksum and the shared_apply that moves it are separate packets, so any
	// in-flight mutation shows up here as a brief skew that closes by itself a
	// frame or two later. Only a mismatch that SURVIVES is worth a multi-megabyte
	// world restream (which also replaces the replica's whole state stack). At the
	// heartbeat's ~2 kHz this still detects a real desync in a couple of seconds.
	const int64_t nowMs = steadyMs();
	if (g_mismatchSinceMs < 0) g_mismatchSinceMs = nowMs;
	if (nowMs - g_mismatchSinceMs < RESYNC_DEBOUNCE_MS) return;

	if (!g_mismatchLogged)
	{
		// once per episode - see g_mismatchLogged
		g_mismatchLogged = true;
		Log(LOG_WARNING) << "[SHARED] world checksum mismatch (persisted "
			<< RESYNC_DEBOUNCE_MS << "ms): "
			<< "funds host=" << hostFunds << " replica=" << myFunds
			<< ", bases host=" << hostBases << " replica=" << myBases
			<< ", research host=" << hostResearch << " replica=" << myResearch
			<< ", items host=" << hostItems << " replica=" << myItems
			<< ", soldiers host=" << hostSoldiers << " replica=" << mySoldiers
			<< ", transfers host=" << hostTransfers << " replica=" << myTransfers
			<< ", production host=" << hostProductions << " replica=" << myProductions
			<< ", sites host=" << hostSites << " replica=" << mySites
			<< ", content (stores/projects/counters/events/soldier stats) agree="
			<< contentAgrees("chkStores", myStores) << contentAgrees("chkProjects", myProjects)
			<< contentAgrees("chkCounters", myCounters) << contentAgrees("chkEvents", myEvents)
			<< contentAgrees("chkSoldierStats", mySoldierStats);
		if (separate)
			Log(LOG_WARNING) << "[SHARED] Separate player terms: wallets host="
				<< namedTermsText(hostPlayerFunds) << " replica=" << namedTermsText(myPlayerFunds)
				<< ", research host=" << namedTermsText(hostPlayerResearch)
				<< " replica=" << namedTermsText(myPlayerResearch);
	}

	const int64_t now = gameMinutes(save);
	const bool cooling = (g_lastResyncGameMin >= 0 && now >= 0
		&& now - g_lastResyncGameMin < RESYNC_COOLDOWN_MINUTES);

	if (g_resyncPending)
	{
		// A restream is already on the wire: every heartbeat until it lands still
		// mismatches, and re-asking would make the host drop the request ("streamer
		// busy") or serialize the whole world twice. Wait for the adoption. The wait
		// is REAL time since the last sign of the stream (the request, its mark or a
		// chunk): at the fastest speed many game hours pass while a large world
		// streams, so a game-time guard expired mid-stream. A request that shows no
		// progress for RESYNC_PENDING_TIMEOUT_MS was dropped or died: ask again. That
		// repair never landed, so it does not count toward giving up below.
		if (nowMs - g_streamProgressMs < RESYNC_PENDING_TIMEOUT_MS) return;
		Log(LOG_WARNING) << "[SHARED] no world stream within "
			<< RESYNC_PENDING_TIMEOUT_MS << "ms of the resync request; asking again";
		g_resyncPending = false;
		requestResync(game, "previous resync request got no stream");
		return;
	}

	if (cooling)
	{
		// A resync DID land and we are diverging again inside the cooldown: the
		// auto-repair does not stick, so something is drifting faster than a
		// restream can heal it. Stop looping on multi-megabyte world streams and
		// hand it to the player.
		if (!g_resyncGaveUp)
		{
			g_resyncGaveUp = true;
			Log(LOG_ERROR) << "[SHARED] world desync persisted through an auto-resync"
				<< " (within " << RESYNC_COOLDOWN_MINUTES << " game minutes);"
				<< " automatic repair disabled - advise the host to save and reload";
			showFail(game, "Desync repair failed. Ask the host to save and reload the campaign.");
		}
		return;
	}

	requestResync(game, "world checksum mismatch");
}

void hostWorldExtras(Game* game)
{
	SavedGame* save = game ? game->getSavedGame() : nullptr;
	if (!save || !sharedHost(game)) return;
	static const SavedGame* lastSave = nullptr;
	static int64_t lastEvents = -1, lastCounters = -1;
	const int64_t events = chkEvents(save);
	const int64_t counters = chkCounters(save, game->getMod());
	if (save == lastSave && events == lastEvents && counters == lastCounters) return;
	lastSave = save;
	lastEvents = events;
	lastCounters = counters;

	Json::Value list(Json::arrayValue);
	for (const GeoscapeEvent* ge : save->getGeoscapeEvents())
	{
		if (ge->isOver()) continue;
		Json::Value e;
		e["name"] = ge->getRules().getName();
		e["owner"] = ge->getOwnerPlayerName();
		e["countdown"] = Json::Value::UInt64(ge->getSpawnCountdown());
		e["shared"] = ge->isCoopShared();
		list.append(e);
	}
	Json::Value values(Json::objectValue);
	const auto& ids = save->getAllIds();
	for (const auto& name : customCounterNames(game->getMod()))
	{
		auto it = ids.find(name);
		if (it != ids.end()) values[name] = it->second;
	}
	Json::Value p;
	p["events"] = list;
	p["counters"] = values;
	submitLocalCmd(game, "world_extras", -1, p);
}

namespace {
// world_extras payload: { events: [ {name, owner, countdown, shared} ],
// counters: { name: value } }. The host's whole set; the replica replaces its own.
void worldExtrasApply(Game* game, Json::Value& payload, Base* /*base*/, int /*seat*/)
{
	if (connectionTCP::getHost()) return;
	SavedGame* save = game->getSavedGame();
	Mod* mod = game->getMod();
	if (!save || !mod) return;
	auto& events = save->getGeoscapeEvents();
	for (GeoscapeEvent* ge : events) delete ge;
	events.clear();
	for (const auto& e : payload["events"])
	{
		const RuleEvent* rule = mod->getEvent(e.get("name", "").asString(), false);
		if (!rule) continue;
		GeoscapeEvent* ge = new GeoscapeEvent(*rule);
		ge->setOwnerPlayerName(e.get("owner", "").asString());
		ge->setSpawnCountdown((size_t)e.get("countdown", 30).asUInt64());
		ge->setCoopShared(e.get("shared", false).asBool());
		events.push_back(ge);
	}
	std::map<std::string, int> ids = save->getAllIds();
	const Json::Value& counters = payload["counters"];
	for (const auto& name : customCounterNames(mod))
	{
		if (counters.isMember(name)) ids[name] = counters[name].asInt();
		else ids.erase(name);
	}
	save->setAllIds(ids);
}

std::map<std::string, int> itemCounts(const ItemContainer* items)
{
	std::map<std::string, int> out;
	for (const auto& item : *items->getContents())
		if (item.second != 0) out[item.first->getType()] = item.second;
	return out;
}

// Appends {<keys>, item, delta} for every type whose count changed.
void appendItemDeltas(Json::Value& out, const std::map<std::string, int>& before,
	const std::map<std::string, int>& after, const Json::Value& keys)
{
	std::set<std::string> types;
	for (const auto& item : before) types.insert(item.first);
	for (const auto& item : after) types.insert(item.first);
	for (const auto& type : types)
	{
		auto b = before.find(type), a = after.find(type);
		const int delta = (a == after.end() ? 0 : a->second) - (b == before.end() ? 0 : b->second);
		if (delta == 0) continue;
		Json::Value d = keys;
		d["item"] = type;
		d["delta"] = delta;
		out.append(d);
	}
}

Craft* newRewardCraft(Game* game, Base* base, const Json::Value& c)
{
	const RuleCraft* rule = game->getMod()->getCraft(c.get("type", "").asString(), false);
	if (!rule) return nullptr;
	Craft* craft = new Craft(rule, base, c.get("id", 0).asInt());
	craft->initFixedWeapons(game->getMod());
	craft->setStatus(c.get("status", "STR_READY").asString());
	return craft;
}

Json::Value rewardCraft(Craft* craft)
{
	Json::Value c;
	c["type"] = craft->getRules()->getType();
	c["id"] = craft->getId();
	c["status"] = craft->getStatus();
	return c;
}
} // namespace

EventRewardSnapshot snapshotEventRewards(Game* game, Base* hq)
{
	EventRewardSnapshot s;
	SavedGame* save = game ? game->getSavedGame() : nullptr;
	if (!save || !hq || !game->getCoopMod() || !game->getCoopMod()->isSeparateCampaign()
		|| !game->getCoopMod()->getServerOwner())
		return s;
	s.active = true;
	for (Base* base : *save->getBases())
	{
		s.stores.push_back(itemCounts(base->getStorageItems()));
		std::vector<std::map<std::string, int> > crafts;
		for (Craft* craft : *base->getCrafts())
			crafts.push_back(itemCounts(craft->getItems()));
		s.craftItems.push_back(crafts);
	}
	s.hqTransfers = hq->getTransfers()->size();
	s.hqCrafts = hq->getCrafts()->size();
	return s;
}

std::string describeEventRewards(Game* game, Base* hq, const EventRewardSnapshot& before)
{
	SavedGame* save = game ? game->getSavedGame() : nullptr;
	if (!before.active || !save || !hq) return std::string();
	const auto& bases = *save->getBases();
	// eventLogic adds no base; a base list that changed is left to the checksum.
	if (bases.size() != before.stores.size()) return std::string();
	int hqIdx = -1;
	Json::Value stores(Json::arrayValue), craftItems(Json::arrayValue);
	for (size_t i = 0; i < bases.size(); ++i)
	{
		if (bases[i] == hq) hqIdx = (int)i;
		Json::Value keys;
		keys["baseIdx"] = (int)i;
		appendItemDeltas(stores, before.stores[i], itemCounts(bases[i]->getStorageItems()), keys);
		const auto& crafts = *bases[i]->getCrafts();
		for (size_t j = 0; j < before.craftItems[i].size() && j < crafts.size(); ++j)
		{
			Json::Value craftKeys = keys;
			craftKeys["craftId"] = crafts[j]->getId();
			craftKeys["craftType"] = crafts[j]->getRules()->getType();
			appendItemDeltas(craftItems, before.craftItems[i][j], itemCounts(crafts[j]->getItems()),
				craftKeys);
		}
	}
	if (hqIdx < 0) return std::string();
	Json::Value transfers(Json::arrayValue), crafts(Json::arrayValue), ids(Json::objectValue);
	const auto& hqTransfers = *hq->getTransfers();
	for (size_t i = before.hqTransfers; i < hqTransfers.size(); ++i)
	{
		Transfer* t = hqTransfers[i];
		Json::Value d;
		d["type"] = (int)t->getType();
		d["hours"] = t->getHours();
		d["owner"] = t->getOwnerPlayerName();
		d["qty"] = t->getQuantity();
		// By type: a Transfer leaves the members of the other kinds unset.
		if (t->getType() == TRANSFER_ITEM && t->getItems())
			d["item"] = t->getItems()->getType();
		if (t->getType() == TRANSFER_CRAFT && t->getCraft())
		{
			d["craft"] = rewardCraft(t->getCraft());
			ids[t->getCraft()->getRules()->getType()] = 0;
		}
		if (t->getType() == TRANSFER_SOLDIER && t->getSoldier())
			d["soldier"] = serializeSoldier(game, t->getSoldier());
		transfers.append(d);
	}
	const auto& hqCrafts = *hq->getCrafts();
	for (size_t i = before.hqCrafts; i < hqCrafts.size(); ++i)
	{
		crafts.append(rewardCraft(hqCrafts[i]));
		ids[hqCrafts[i]->getRules()->getType()] = 0;
	}
	// The host minted the new crafts' ids; the replica's id counters follow.
	const auto& allIds = save->getAllIds();
	for (const std::string& type : ids.getMemberNames())
	{
		auto it = allIds.find(type);
		if (it != allIds.end()) ids[type] = it->second;
		else ids.removeMember(type);
	}
	if (stores.empty() && craftItems.empty() && transfers.empty() && crafts.empty())
		return std::string();
	Json::Value r;
	r["baseIdx"] = hqIdx;
	r["stores"] = stores;
	r["craftItems"] = craftItems;
	r["transfers"] = transfers;
	r["crafts"] = crafts;
	r["ids"] = ids;
	return r.toStyledString();
}

void applyEventRewards(Game* game, const Json::Value& r)
{
	SavedGame* save = game ? game->getSavedGame() : nullptr;
	Mod* mod = game ? game->getMod() : nullptr;
	if (!save || !mod || !r.isObject() || connectionTCP::getHost()) return;
	for (const auto& d : r["stores"])
	{
		Base* base = resolveBase(game, d.get("baseIdx", -1).asInt());
		const RuleItem* item = mod->getItem(d.get("item", "").asString(), false);
		const int delta = d.get("delta", 0).asInt();
		if (!base || !item) continue;
		if (delta > 0) base->getStorageItems()->addItem(item, delta);
		else base->getStorageItems()->removeItem(item, -delta);
	}
	for (const auto& d : r["craftItems"])
	{
		Base* base = resolveBase(game, d.get("baseIdx", -1).asInt());
		Craft* craft = base ? findCraft(base, d.get("craftId", -1).asInt(),
			d.get("craftType", "").asString()) : nullptr;
		const RuleItem* item = mod->getItem(d.get("item", "").asString(), false);
		const int delta = d.get("delta", 0).asInt();
		if (!craft || !item) continue;
		if (delta > 0) craft->getItems()->addItem(item, delta);
		else craft->getItems()->removeItem(item, -delta);
	}
	Base* hq = resolveBase(game, r.get("baseIdx", -1).asInt());
	if (!hq) return;
	const Json::Value& ids = r["ids"];
	if (ids.isObject() && !ids.empty())
	{
		std::map<std::string, int> all = save->getAllIds();
		for (const std::string& type : ids.getMemberNames()) all[type] = ids[type].asInt();
		save->setAllIds(all);
	}
	for (const auto& c : r["crafts"])
		if (Craft* craft = newRewardCraft(game, hq, c))
			hq->getCrafts()->push_back(craft);
	for (const auto& d : r["transfers"])
	{
		Transfer* t = new Transfer(d.get("hours", 1).asInt());
		t->setOwnerPlayerName(d.get("owner", "").asString());
		const int qty = d.get("qty", 1).asInt();
		bool made = true;
		switch (d.get("type", -1).asInt())
		{
		case TRANSFER_ITEM:
			if (const RuleItem* item = mod->getItem(d.get("item", "").asString(), false))
				t->setItems(item, qty);
			else made = false;
			break;
		case TRANSFER_SCIENTIST: t->setScientists(qty); break;
		case TRANSFER_ENGINEER: t->setEngineers(qty); break;
		case TRANSFER_CRAFT:
			if (Craft* craft = newRewardCraft(game, hq, d["craft"])) t->setCraft(craft);
			else made = false;
			break;
		case TRANSFER_SOLDIER:
			if (Soldier* s = deserializeSoldier(game, d.get("soldier", "").asString()))
				t->setSoldier(s);
			else made = false;
			break;
		default: made = false;
		}
		if (made) hq->getTransfers()->push_back(t);
		else delete t;
	}
}

void noteWorldStreamProgress()
{
	// A chunk of a world stream arrived. A large world takes many seconds to
	// stream; the in-flight resync guard and the result hold live while chunks
	// keep coming.
	if (g_resyncPending || g_restreamMarks > 0) g_streamProgressMs = steadyMs();
}

void sendRestreamMark(Game* game)
{
	if (!game || !game->getCoopMod()) return;
	Json::Value mark;
	// Separate keeps its own wire namespace (SeparateEcon.h).
	mark["state"] = game->getCoopMod()->isSeparateCampaign()
		? "separate_restream_mark" : "shared_restream_mark";
	game->getCoopMod()->sendTCPPacketData(mark.toStyledString());
}

void beginRestreamHold()
{
	// Anything still held was sent before this newer snapshot, so it is in it.
	const size_t inSnapshot = g_heldResults.size();
	g_heldResults.clear();
	g_releaseHeld = false;
	++g_restreamMarks;
	g_streamProgressMs = steadyMs();
	Log(LOG_INFO) << "[SHARED] restream mark: host results wait for the adopted world ("
		<< inSnapshot << " earlier held result(s) are in this snapshot)";
}

bool holdResultDuringRestream(const std::string& state, const Json::Value& obj)
{
	if (g_restreamMarks <= 0 && !g_releaseHeld) return false;
	// The host's world results: every command result (production, research,
	// research_effects, world_extras, ...) rides shared_apply / separate_apply; the
	// Separate event and mission-research results change the world on receipt.
	if (state != "shared_apply" && state != "separate_apply"
		&& state != "separate_geoscape_event" && state != "separate_mission_research")
		return false;
	g_heldResults.emplace_back(state, obj);
	return true;
}

void releaseHeldResults(Game* game)
{
	bool timedOut = false;
	if (g_restreamMarks > 0 && !g_releaseHeld
		&& steadyMs() - g_streamProgressMs >= RESYNC_PENDING_TIMEOUT_MS)
	{
		// The marked world never landed (a failed load or a lost stream). Do not sit
		// on the results forever: apply them to the world this replica has, and let
		// the checksum repair whatever that leaves.
		Log(LOG_WARNING) << "[SHARED] restream not adopted within "
			<< RESYNC_PENDING_TIMEOUT_MS << "ms; applying " << g_heldResults.size()
			<< " held result(s) to the current world";
		g_restreamMarks = 0;
		g_releaseHeld = true;
		timedOut = true;
	}
	if (!g_releaseHeld) return;
	g_releaseHeld = false;
	std::deque<std::pair<std::string, Json::Value>> held;
	held.swap(g_heldResults);
	if (held.empty() || !game || !game->getCoopMod()) return;
	if (!timedOut)
		Log(LOG_INFO) << "[SHARED] restream adopted: applying " << held.size()
			<< " result(s) held during the restream";
	for (auto& result : held)
	{
		game->getCoopMod()->onTCPMessage(result.first, result.second);
		// An event result changes the world on receipt, while an apply waits in
		// g_applyQ. Drain after each one so the held results apply in arrival
		// order: an apply carries absolute funds, so a day_tick applied after a
		// later event would undo that event's funds.
		for (;;)
		{
			Json::Value ap;
			{
				std::lock_guard<std::mutex> lk(g_mx);
				if (g_applyQ.empty()) break;
				ap = std::move(g_applyQ.front());
				g_applyQ.pop_front();
			}
			processApply(game, ap);
		}
	}
}

void resetRestreamHold()
{
	g_restreamMarks = 0;
	g_releaseHeld = false;
	g_heldResults.clear();
}

ResyncStats resyncStats()
{
	ResyncStats s;
	s.mismatches = g_mismatchN.load();
	s.requests = g_resyncReqN.load();
	s.pending = g_resyncPending;
	s.gaveUp = g_resyncGaveUp;
	s.lastGameMin = g_lastResyncGameMin;
	return s;
}

void resetResyncStats()
{
	g_mismatchN = 0;
	g_resyncReqN = 0;
	g_resyncPending = false;
	g_resyncGaveUp = false;
	g_mismatchLogged = false;
	g_mismatchSinceMs = -1;
	g_lastResyncGameMin = -1;
}

// ===== battle hash buckets =====
// DEFINITIONS ONLY: the FNV mixer, the tile-inclusion test and the saveBlob
// node-tree walk + FOW bin-tiles masking. No ring, compare, side-gate,
// promotion-table or boundary-persistence machinery: there is no host-side
// ring to compare against (the host never compares).

namespace
{

const std::uint64_t FNV_OFFSET = 1469598103934665603ULL;
const std::uint64_t FNV_PRIME = 1099511628211ULL;

inline std::uint64_t mix(std::uint64_t h, std::int64_t v)
{
	return (h ^ (std::uint64_t)v) * FNV_PRIME;
}

std::uint64_t fnv1a(const std::string& s)
{
	std::uint64_t h = FNV_OFFSET;
	for (char c : s)
	{
		h ^= (std::uint64_t)(unsigned char)c;
		h *= FNV_PRIME;
	}
	return h;
}

// As in older versions' unitLiveness(): STANDING/WALKING/FLYING/... are
// animation phases the two machines are never on the same frame of - what
// must agree is on-feet / dead / unconscious / ignored.
int unitLiveness(const BattleUnit* unit)
{
	switch (unit->getStatus())
	{
	case STATUS_DEAD:        return 1;
	case STATUS_UNCONSCIOUS: return 2;
	case STATUS_IGNORE_ME:   return 3;
	default:                 return 0;
	}
}

// the `synced` bucket's script-tag form - the raw
// script-value vector with trailing zeros stripped, exactly as the delta's
// `tags` ships it (CoopDelta's stripTags), mixed as size then values.
std::uint64_t mixSyncedTags(std::uint64_t h, std::vector<int> tags)
{
	while (!tags.empty() && tags.back() == 0)
		tags.pop_back();
	h = mix(h, (std::int64_t)tags.size());
	for (int v : tags)
		h = mix(h, v);
	return h;
}

} // namespace

const char* battleHashBucketName(int i)
{
	static const char* const kNames[BATTLE_HASH_BUCKETS] =
	{
		"terrain", "fire", "smoke", "items", "unitsCore", "unitsStats", "itemIdCtr",
		"synced",
	};
	return (i >= 0 && i < BATTLE_HASH_BUCKETS) ? kNames[i] : "?";
}

std::uint64_t battleHashBucketValue(const BattleHashSet& h, int i)
{
	switch (i)
	{
	case 0: return h.terrain;
	case 1: return h.fire;
	case 2: return h.smoke;
	case 3: return h.items;
	case 4: return h.unitsCore;
	case 5: return h.unitsStats;
	case 6: return h.itemIdCtr;
	case 7: return h.synced;
	default: return 0;
	}
}

bool computeBattleHashes(SavedBattleGame* battle, BattleHashSet& out)
{
	out.terrain = out.fire = out.smoke = out.items = 0;
	out.unitsCore = out.unitsStats = out.itemIdCtr = 0;
	out.synced = 0;
	if (!battle)
		return false;

	// `synced` = every delta
	// field no other bucket covers (33 rows), in the same sweep. Per entity an
	// FNV that first mixes a kind tag (1 unit, 2 tile, 3 node, 4 item,
	// 5 battle) and the id/index, then the fields in a fixed order,
	// summed like every other bucket (order-free). FIELD-PARITY:
	// connectionTCP.cpp's CoopDelta captureUnit/captureTile/captureItem/
	// captureBattle read exactly these getters - a field added there joins a
	// legacy bucket or this one in the same commit.

	// --- tiles: terrain, fire, smoke ---------------------------------------
	// A VOID tile (no map-data part AND no explosive accumulator) contributes
	// nothing - the skip is a pure function of the tile's own state, so a
	// tile that went void on one machine only is skipped there and mixed
	// here, and the sums differ (the detection we want).
	const int tileCount = battle->getMapSizeXYZ();
	for (int i = 0; i < tileCount; ++i)
	{
		Tile* tile = battle->getTile(i);
		if (!tile)
			continue;

		bool hasPart = false;
		for (int part = 0; part < O_MAX && !hasPart; ++part)
			hasPart = tile->getMapData((TilePart)part) != nullptr;
		if (hasPart || tile->getExplosive() != 0)
		{
			std::uint64_t h = FNV_OFFSET;
			h = mix(h, i);
			for (int part = 0; part < O_MAX; ++part)
			{
				int mapDataID = -1, mapDataSetID = -1;
				tile->getMapData(&mapDataID, &mapDataSetID, (TilePart)part);
				h = mix(h, mapDataID);
				h = mix(h, mapDataSetID);
			}
			h = mix(h, tile->getExplosive());
			h = mix(h, tile->getExplosiveType());
			out.terrain += h;
		}

		const int f = tile->getFire();
		if (f > 0)
		{
			std::uint64_t h = FNV_OFFSET;
			h = mix(h, i);
			h = mix(h, f);
			out.fire += h;
		}
		const int sm = tile->getSmoke();
		if (sm > 0)
		{
			std::uint64_t h = FNV_OFFSET;
			h = mix(h, i);
			h = mix(h, sm);
			out.smoke += h;
		}

		// synced: doorBits, captureTile's formula; tiles with
		// every UFO-door part closed contribute nothing.
		const int doorBits = (tile->isUfoDoorOpen(O_WESTWALL) ? 1 : 0)
			| (tile->isUfoDoorOpen(O_NORTHWALL) ? 2 : 0)
			| (tile->isUfoDoorOpen(O_FLOOR) ? 4 : 0);
		if (doorBits != 0)
		{
			std::uint64_t y = FNV_OFFSET;
			y = mix(y, 2);
			y = mix(y, i);
			y = mix(y, doorBits);
			out.synced += y;
		}
	}

	// The unit-side special-weapon link
	// (BattleUnit::_specWeapon, written by addLoadedSpecialWeapon /
	// coopDetachSpecialWeapon on the client) has no slot enumerator, so each
	// unit's link is read as the _items entries x with
	// unit->getSpecialWeapon(x's rules) == x - asked once per DISTINCT item rule
	// (getSpecialWeapon(rules) returns the first slot holding that rule, the
	// only one the per-item test can match). Collected by the items sweep below.
	std::set<const RuleItem*> specRules;
	std::set<const BattleItem*> liveItems;

	// --- items: the strict census -------------------------------------------
	// Includes ammoQty and fuse (getFuseTimer()). Ground-strip
	// x/y is a pure client-local Inventory::arrangeGround() display recompute
	// (never replicated) - only INV_SLOT items carry a meaningful x/y,
	// exactly the guard vanilla's own BattleItem::save() already applies.
	for (BattleItem* item : *battle->getItems())
	{
		if (!item)
			continue;
		liveItems.insert(item);
		if (item->getRules())
			specRules.insert(item->getRules());
		std::uint64_t h = FNV_OFFSET;
		h = mix(h, item->getId());
		h ^= fnv1a(item->getRules() ? item->getRules()->getType() : std::string("?"));
		h *= FNV_PRIME;
		h = mix(h, item->getOwner() ? item->getOwner()->getId() : -1);
		const RuleInventory* slot = item->getSlot();
		h ^= fnv1a(slot ? slot->getId() : std::string("-"));
		h *= FNV_PRIME;
		if (slot && slot->getType() == INV_SLOT) // ground/hand carry no x/y
		{
			h = mix(h, item->getSlotX());
			h = mix(h, item->getSlotY());
		}
		const Tile* t = item->getTile();
		h = mix(h, t ? t->getPosition().x : -1);
		h = mix(h, t ? t->getPosition().y : -1);
		h = mix(h, t ? t->getPosition().z : -1);
		h = mix(h, item->getFuseTimer());
		h = mix(h, item->getAmmoQuantity()); // ammoQty
		out.items += h;

		// synced: captureItem's getters.
		std::uint64_t y = FNV_OFFSET;
		y = mix(y, 4);
		y = mix(y, item->getId());
		y = mix(y, item->getPreviousOwner() ? item->getPreviousOwner()->getId() : -1);
		y = mix(y, item->getUnit() ? item->getUnit()->getId() : -1);
		for (int k = 0; k < RuleItem::AmmoSlotMax; ++k)
		{
			const BattleItem* a = item->getAmmoForSlot(k);
			y = mix(y, a ? a->getId() : -1); // self = the item's own id
		}
		y = mix(y, item->isFuseEnabled() ? 1 : 0);
		y = mix(y, item->getPainKillerQuantity());
		y = mix(y, item->getHealQuantity());
		y = mix(y, item->getStimulantQuantity());
		y = mix(y, item->getTurnFlag() ? 1 : 0);
		y = mix(y, item->getXCOMProperty() ? 1 : 0);
		y = mixSyncedTags(y, item->coopScriptValuesRaw());
		out.synced += y;
	}

	// --- units: core identity/liveness/position, then unitsStats ------------
	// unitsStats is the RE-MERGED single bucket (legacy unitsCombat/
	// unitsRegen fold back in) - tu, energy, health, stun, morale, mana,
	// fire, kneeling, mcId, wounds, motionPoints.
	for (BattleUnit* unit : *battle->getUnits())
	{
		if (!unit)
			continue;
		const Position p = unit->getPosition();

		std::uint64_t c = FNV_OFFSET;
		c = mix(c, unit->getId());
		c = mix(c, (int)unit->getFaction());
		c = mix(c, unitLiveness(unit));
		c = mix(c, p.x);
		c = mix(c, p.y);
		c = mix(c, p.z);
		out.unitsCore += c;

		std::uint64_t s = FNV_OFFSET;
		s = mix(s, unit->getId());
		s = mix(s, unit->getTimeUnits());
		s = mix(s, unit->getEnergy());
		s = mix(s, unit->getHealth());
		s = mix(s, unit->getStunlevel());
		s = mix(s, unit->getMorale());
		s = mix(s, unit->getMana());
		s = mix(s, unit->getFire());
		s = mix(s, unit->isKneeled() ? 1 : 0);
		s = mix(s, unit->getMindControllerId());
		for (int part = 0; part < BODYPART_MAX; ++part)
			s = mix(s, unit->getFatalWound((UnitBodyPart)part));
		s = mix(s, unit->getMotionPoints());
		out.unitsStats += s;

		// synced: captureUnit's getters;
		// `status` raw, unitsCore keeps liveness.
		std::uint64_t y = FNV_OFFSET;
		y = mix(y, 1);
		y = mix(y, unit->getId());
		y = mix(y, unit->getTile() != nullptr ? 1 : 0);
		y = mix(y, unit->getDirection());
		y = mix(y, unit->getTurretDirection());
		y = mix(y, (int)unit->getStatus());
		y = mix(y, unit->isFloating() ? 1 : 0);
		for (int side = 0; side < (int)SIDE_MAX; ++side)
			y = mix(y, unit->getArmor((UnitSide)side));
		y = mix(y, unit->wantsToSurrender() ? 1 : 0);
		y = mix(y, unit->isSurrendering() ? 1 : 0);
		y = mix(y, unit->coopGetMoraleRestored());
		y ^= fnv1a(unit->getSpawnUnit() ? unit->getSpawnUnit()->getType() : std::string());
		y *= FNV_PRIME;
		y = mix(y, unit->getRespawn() ? 1 : 0);
		y = mix(y, (int)unit->getSpawnUnitFaction());
		y = mix(y, unit->getAlreadyRespawned() ? 1 : 0);
		y ^= fnv1a(unit->isRightHandPreferredForReactions() ? std::string("STR_RIGHT_HAND")
			: (unit->isLeftHandPreferredForReactions() ? std::string("STR_LEFT_HAND") : std::string()));
		y *= FNV_PRIME;
		y = mix(y, unit->isLeftHandDisabledForReactions() ? 1 : 0);
		y = mix(y, unit->isRightHandDisabledForReactions() ? 1 : 0);
		y = mixSyncedTags(y, unit->coopScriptValuesRaw());
		// captureUnit's two names (equal on both machines at battle start) - the unit's own stored name and its geoscape Soldier's
		// raw name ("" without one) - in this function's own string mix.
		y ^= fnv1a(unit->getName(nullptr));
		y *= FNV_PRIME;
		y ^= fnv1a(unit->getGeoscapeSoldier() ? unit->getGeoscapeSoldier()->getName(false) : std::string());
		y *= FNV_PRIME;
		// FIELD-PARITY: captureUnit's seat tag, after the names.
		y = mix(y, (int)unit->getCoopSeat());
		// the unit's special-weapon link - the ids
		// of the _items entries its own slots hold, ascending, as size then ids.
		{
			std::vector<int> spec;
			for (const RuleItem* rule : specRules)
			{
				const BattleItem* w = unit->getSpecialWeapon(rule);
				if (w && liveItems.count(w))
					spec.push_back(w->getId());
			}
			std::sort(spec.begin(), spec.end());
			y = mix(y, (std::int64_t)spec.size());
			for (int sid : spec)
				y = mix(y, sid);
		}
		out.synced += y;
	}

	// synced: every node's type.
	if (std::vector<Node*>* nodes = battle->getNodes())
	{
		for (Node* node : *nodes)
		{
			if (!node)
				continue;
			std::uint64_t y = FNV_OFFSET;
			y = mix(y, 3);
			y = mix(y, node->getID());
			y = mix(y, node->getType());
			out.synced += y;
		}
	}

	// synced: the battle as one entity, captureBattle's
	// getters; moduleMap cells x-major (x, y, first, second).
	{
		std::uint64_t y = FNV_OFFSET;
		y = mix(y, 5);
		y = mix(y, 0);
		y = mix(y, battle->coopGetObjectivesDestroyed());
		const auto& moduleMap = battle->getModuleMap();
		for (size_t x = 0; x < moduleMap.size(); ++x)
		{
			for (size_t my = 0; my < moduleMap[x].size(); ++my)
			{
				y = mix(y, (std::int64_t)x);
				y = mix(y, (std::int64_t)my);
				y = mix(y, moduleMap[x][my].first);
				y = mix(y, moduleMap[x][my].second);
			}
		}
		y = mix(y, battle->getBughuntMode() ? 1 : 0);
		y = mix(y, battle->getTurn());
		y = mix(y, (int)battle->getSide());
		y = mixSyncedTags(y, battle->coopScriptValuesRaw());
		// reinforcementsMemory, captureBattle's getter -
		// size, then each {wave type, count} in the map's own (key) order.
		const std::map<std::string, int>& rm = battle->getReinforcementsMemory();
		y = mix(y, (std::int64_t)rm.size());
		for (const auto& kv : rm)
		{
			y ^= fnv1a(kv.first);
			y *= FNV_PRIME;
			y = mix(y, kv.second);
		}
		out.synced += y;
	}

	out.itemIdCtr = (std::uint64_t)(std::int64_t)*battle->getCurrentItemId();
	return true;
}

// ----- the saveBlob (whole-document) hash --------

namespace
{

// Which top-level array (if any) the current node-tree walk descended from -
// needed for exactly one scope-gated exclusion (previousOwner, see below).
enum class SbScope { Other, Unit, Item, Node };

// TOP-LEVEL of the battle document only (SavedBattleGame-scoped, per-seat UI/
// display/audio-transient/battle-end-adjacent fields), PLUS the two
// BriefingState display labels (see below).
bool saveBlobExcludedTopKey(std::string_view k)
{
	return k == "nameDisplay"
		|| k == "selectedUnit" || k == "undoUnit"
		// PER-MACHINE RESERVE SETTINGS (a contract, not code). These two exclusions are
		// LOAD-BEARING, not housekeeping: they are what makes each player's TU/
		// kneel reserve THEIR OWN. Because no bucket reads them, two machines
		// may legitimately hold different values forever, which is why the
		// reserve buttons are deliberately NOT coop-gated
		// (BattlescapeState::btnReserveKneelClick carries the other half of this
		// note) and why no `reserve` field goes on the wire. The knock-on rules
		// are fixed: the host does NOT apply its own reserve to a
		// CLIENT-origin walk, and the client checks its own reserve per step when
		// it builds the walk intent, because vanilla's sole enforcement point
		// (UnitWalkBState.cpp:324) runs on the host - Pathfinding::previewPath
		// only COLOURS tiles (Pathfinding.cpp:1269 -> :1303), it never refuses.
		// Do not remove these two entries.
		|| k == "tuReserved" || k == "kneelReserved"
		// The battle's
		// TURN MODE. Session CONFIGURATION, not simulated state - both machines
		// already agree on it because the host stamps it on battle_offer and the
		// client mirrors it, so it must never ride the saveBlob hash. Same
		// treatment, and the same reason, as the two BriefingState labels below.
		|| k == "coopTurnMode"
		// the mission
		// deployment label and the traditional-mode baton holder - both
		// machines already agree on the value via the offer (a disk resume
		// carries it in the battle block instead), same treatment as
		// coopTurnMode above.
		|| k == "coopDeployment" || k == "coopActiveSeat"
		// the host's carried item-id counter. Both
		// machines write the same value once the adopt works, so this is
		// belt-and-braces - but it also keeps a legitimately different value
		// from redding saveBlob instead of the itemIdCtr bucket that is
		// supposed to report it.
		|| k == "coopItemIdCtr"
		|| k == "togglePersonalLight" || k == "toggleNightVision" || k == "toggleBrightness"
		|| k == "animFrame"
		|| k == "currentAmbienceDelay"
		|| k == "vipsSaved" || k == "vipsSavedScore"
		|| k == "vipsLost" || k == "vipsLostScore"
		|| k == "vipsWaitingOutside" || k == "vipsWaitingOutsideScore"
		// Found by a divergence hunt: at the time, the ONLY unexcluded
		// saveBlob divergence in a live coop battle. Both are DISPLAY-ONLY
		// briefing/HUD labels ("LANDING SITE-0", "CRAFT> SKYRANGER-1"), written by
		// BriefingState (BriefingState.cpp:151-188). The host ran BriefingState;
		// the thin client loaded the streamed blob straight to BattlescapeState
		// (no briefing), so they stayed empty on the client. No sim effect - same
		// per-battle display class as the excluded unit fields (saveBlobExcludedUnitKey).
		//
		// The underlying gap is closed: the
		// host now mints both labels BEFORE the offer and battle_offer.missionLabel
		// carries them, so the two machines agree on them in real play. THE
		// EXCLUSION STAYS, and is now load-bearing in the other direction: it is
		// what makes carrying the labels hash-neutral by construction, so a future
		// label change can never make a bucket differ. Do not "clean it up" now that the
		// values happen to match.
		|| k == "strTarget" || k == "strCraftOrBase";
}

// ANY DEPTH, but only meaningful (and only ever reached) inside a "units"
// array element (see the SbScope::Unit gate at the call site): legacy
// kills/exp*/tempUnitStatistics, the per-unit FOV fields visible/turnsSinceSpotted*,
// and the other fields listed below. previousOwner
// collides with BattleItem's OWN previousOwner field (which must stay
// hashed) - it is scope-gated separately at
// the call site instead of listed here, so this function alone is never
// depth-ambiguous.
bool saveBlobExcludedUnitKey(std::string_view k)
{
	return k == "kills"
		|| k == "expBravery" || k == "expReactions" || k == "expFiring" || k == "expThrowing"
		|| k == "expPsiSkill" || k == "expPsiStrength" || k == "expMana" || k == "expMelee"
		|| k == "tempUnitStatistics"
		|| k == "visible"
		|| k == "turnsSinceSpotted" || k == "turnsSinceSpottedByXcom" || k == "turnsSinceSpottedByCivilian"
		|| k == "turnsLeftSpottedForSnipers" || k == "turnsLeftSpottedForSnipersByXcom"
		|| k == "turnsLeftSpottedForSnipersByCivilian"
		|| k == "turnsSinceStunned"
		|| k == "dontReselect"
		|| k == "aiMedikitUsed"
		// a client runs no AI. The whole AIModule::save() map -
		// fromNode, toNode, AIMode, wasHitBy, weaponPickedUp, targetFaction -
		// is written under the unit (BattleUnit.cpp:767) only on the machine
		// that ran think(), so it is host-only by construction.
		|| k == "AI"
		|| k == "activeHand"
		|| k == "notificationShown"
		|| k == "killedBy"
		|| k == "customMarker"
		|| k == "murdererId"
		|| k == "fatalShotSide" || k == "fatalShotBodyPart"
		|| k == "murdererWeapon" || k == "murdererWeaponAmmo"
		|| k == "resummonedFakeCivilian"
		|| k == "meleeAttackedBy"
		|| k == "summonedPlayerUnit";
}

// The binTiles FOW bits are NOT masked: revealed tiles are game state,
// authored exclusively by the host and synced as `reveal` deltas
// (CoopReveal.h), and a thin client's own tile-FOV sweep is suppressed
// (TileEngine::calculateTilesInFOV), so the two machines' discovered sets
// must match exactly. binTiles falls through to the scalar branch below and
// its base64 text is hashed whole, discovered bits included, so the saveBlob
// bucket VERIFIES the fog instead of hiding it.
//
// Deterministic FNV-1a over the re-parsed node tree (keys + scalar values in
// document order, recursing maps/seqs) - hashing the STRUCTURE, not raw emit
// bytes, so a whitespace/quoting difference between the two builds cannot
// register as a divergence. @a top marks the battle document's own direct
// children (where the top-level-only exclusions apply); @a scope tracks
// which of four scopes the walk is inside: "units" (the scope-gated
// previousOwner exclusion fires only here), "items"/"itemsSpecial" (where
// BattleItem's own previousOwner field stays hashed), "nodes" (SbScope::Node -
// the allocated flag is skipped here; see below), or Other.
//
// SbScope::Node / nodes[].allocated: the pathfinding node the host's AI
// reserved while it ran think(). A client runs no AI and no wire shape
// carries it, so this flag is host-only by
// construction and cannot be made to match. Every other node
// field (id, position, segment, type, rank, flags, reserved, priority,
// links) stays hashed.
void saveBlobHashTree(const YAML::YamlNodeReader& node, std::uint64_t& h, bool top, SbScope scope)
{
	if (node.isMap())
	{
		for (const auto& child : node.children())
		{
			std::string_view key = child.key();
			if (top && saveBlobExcludedTopKey(key))
				continue;
			if (scope == SbScope::Unit && (saveBlobExcludedUnitKey(key) || key == "previousOwner"))
				continue;
			if (scope == SbScope::Node && key == "allocated")
				continue;

			SbScope childScope = scope;
			if (top)
			{
				if (key == "units") childScope = SbScope::Unit;
				else if (key == "items" || key == "itemsSpecial") childScope = SbScope::Item;
				else if (key == "nodes") childScope = SbScope::Node;
				else childScope = SbScope::Other;
			}

			for (char ch : key) { h ^= (std::uint64_t)(unsigned char)ch; h *= FNV_PRIME; }

			// binTiles is an ordinary scalar node here (no FOW mask special case; see
			// the note above saveBlobHashTree()): its base64 text is hashed whole.
			saveBlobHashTree(child, h, false, childScope);
		}
	}
	else if (node.isSeq())
	{
		for (const auto& child : node.children())
			saveBlobHashTree(child, h, false, scope);
	}
	else
	{
		std::string_view val = node.val();
		for (char ch : val) { h ^= (std::uint64_t)(unsigned char)ch; h *= FNV_PRIME; }
	}
}

} // namespace

bool computeSaveBlobHash(SavedBattleGame* battle, std::uint64_t& out, std::string* yamlOut)
{
	out = 0;
	if (!battle)
		return false;

	// Battle document ONLY (SavedBattleGame::save is self-contained), so none
	// of the geoscape/session/RNG state a full SavedGame::save would drag in
	// is ever hashed.
	YAML::YamlRootNodeWriter writer;
	writer.setAsMap();
	battle->save(writer["battle"]);
	YAML::YamlString text = writer.emit();

	// Re-parse and hash the STRUCTURE, so emit-formatting differences between
	// the two builds cannot register as a divergence.
	{
		YAML::YamlRootNodeReader reader(text, "saveBlob");
		std::uint64_t h = FNV_OFFSET;
		saveBlobHashTree(reader["battle"], h, true, SbScope::Other);
		out = h;
	}
	// the hashed document for the desync diagnostics. The
	// reader parsed into its own arena and is gone, so the text can move out.
	if (yamlOut)
		*yamlOut = std::move(text.yaml);
	return true;
}

// ----- minimal desync diagnostic bundle -----------------------

namespace
{

std::string desyncTimeString()
{
	std::time_t t = std::time(nullptr);
	std::tm local{};
	if (const std::tm* p = std::localtime(&t))
		local = *p;
	char buf[32] = { 0 };
	std::strftime(buf, sizeof(buf), "%Y%m%d-%H%M%S", &local);
	return std::string(buf);
}

// Best-effort, never throws: a capped tail of the log file, or an empty
// string if unreadable. Plain ifstream (binary) - no new SDL dependency for
// a 2-3 member bundle.
std::string readLogTail(size_t maxBytes)
{
	std::ifstream f(CrossPlatform::getLogFileName(), std::ios::binary | std::ios::ate);
	if (!f)
		return std::string();
	const std::streamoff size = f.tellg();
	if (size < 0)
		return std::string();
	const std::streamoff from = (maxBytes != 0 && (size_t)size > maxBytes)
		? (size - (std::streamoff)maxBytes) : 0;
	f.seekg(from);
	std::string out((size_t)(size - from), '\0');
	f.read(&out[0], (std::streamsize)out.size());
	return out;
}

// One zip from in-memory members (the writeZipArchive format of older
// versions). Heap writer only.
bool writeZipArchive(const std::string& path,
	const std::vector<std::pair<std::string, std::string>>& members)
{
	if (members.empty())
		return false;
	mz_zip_archive zip;
	std::memset(&zip, 0, sizeof(zip));
	if (!mz_zip_writer_init_heap(&zip, 0, 256 * 1024))
		return false;

	bool ok = true;
	for (size_t i = 0; ok && i < members.size(); ++i)
	{
		ok = (mz_zip_writer_add_mem(&zip, members[i].first.c_str(),
			members[i].second.data(), members[i].second.size(),
			MZ_DEFAULT_COMPRESSION) != MZ_FALSE);
	}

	void* buf = nullptr;
	size_t size = 0;
	if (ok)
		ok = (mz_zip_writer_finalize_heap_archive(&zip, &buf, &size) != MZ_FALSE);
	if (ok && buf != nullptr && size != 0)
	{
		const unsigned char* first = (const unsigned char*)buf;
		std::vector<unsigned char> bytes(first, first + size);
		ok = CrossPlatform::writeFile(path, bytes);
	}
	if (buf)
		mz_free(buf);
	mz_zip_writer_end(&zip);
	return ok;
}

} // namespace

std::string writeDesyncBundle(const std::string& bucket, const std::string& expect,
	const std::string& got, std::uint32_t seq, const std::string& kind,
	const std::string* saveBlobYaml, const char* role, const std::string& peerBundlePath)
{
	try
	{
		const std::string dir = Options::getUserFolder() + "desync-reports/";
		if (!CrossPlatform::folderExists(dir))
			CrossPlatform::createFolder(dir);
		if (!CrossPlatform::folderExists(dir))
		{
			Log(LOG_ERROR) << "[coop-hash] desync bundle: cannot create " << dir;
			return std::string();
		}
		const std::string path = dir + "desync-" + desyncTimeString() + ".zip";

		Json::Value info(Json::objectValue);
		info["bucket"] = bucket;
		info["expect"] = expect;
		info["got"] = got;
		info["seq"] = seq;
		info["kind"] = kind;
		info["timestamp"] = desyncTimeString();
		info["role"] = role ? role : "client"; // coop: the reporting machine's role
		if (!peerBundlePath.empty())
			info["peerBundlePath"] = peerBundlePath;

		std::vector<std::pair<std::string, std::string>> members;
		members.push_back(std::make_pair(std::string("desync-info.json"), info.toStyledString()));
		const std::string logTail = readLogTail(256 * 1024);
		if (!logTail.empty())
			members.push_back(std::make_pair(std::string("openxcom.log"), logTail));
		// a `saveBlob` mismatch names no field by itself;
		// this machine's own battle document goes with the report.
		if (saveBlobYaml && !saveBlobYaml->empty())
			members.push_back(std::make_pair(std::string("saveBlob-") + (role ? role : "client") + ".yaml", *saveBlobYaml));

		if (!writeZipArchive(path, members))
		{
			Log(LOG_ERROR) << "[coop-hash] desync bundle: failed to write " << path;
			return std::string();
		}
		Log(LOG_ERROR) << "[coop-hash] desync diagnostic bundle written to " << path;
		return path;
	}
	catch (const std::exception& e)
	{
		Log(LOG_ERROR) << "[coop-hash] desync bundle failed: " << e.what();
		return std::string();
	}
	catch (...)
	{
		Log(LOG_ERROR) << "[coop-hash] desync bundle failed";
		return std::string();
	}
}

std::string writeDesyncText(const std::string& suffix, const std::string& text)
{
	try
	{
		const std::string dir = Options::getUserFolder() + "desync-reports/";
		if (!CrossPlatform::folderExists(dir))
			CrossPlatform::createFolder(dir);
		if (!CrossPlatform::folderExists(dir))
		{
			Log(LOG_ERROR) << "[coop-hash] desync text: cannot create " << dir;
			return std::string();
		}
		const std::string path = dir + "desync-" + desyncTimeString() + "-" + suffix;
		if (!CrossPlatform::writeFile(path, text))
		{
			Log(LOG_ERROR) << "[coop-hash] desync text: failed to write " << path;
			return std::string();
		}
		Log(LOG_ERROR) << "[coop-hash] desync text written to " << path;
		return path;
	}
	catch (const std::exception& e)
	{
		Log(LOG_ERROR) << "[coop-hash] desync text failed: " << e.what();
		return std::string();
	}
	catch (...)
	{
		Log(LOG_ERROR) << "[coop-hash] desync text failed";
		return std::string();
	}
}

// ===== coop: the next-launch crash reporter. The formatted time string is crashTimeString(const char*) here (this
// file's anonymous namespace already holds a no-argument desyncTimeString()), and the zip goes through this file's
// writeZipArchive() (the miniz heap writer). =====
namespace {

// SAFETY / bounded work: the log is the only member that can grow without limit,
// so only its TAIL travels. 4 MB is many times a whole battle's worth of co-op
// tracing and keeps the one-shot compress step to a few hundred ms on the single
// frame this ever runs.
const size_t DESYNC_LOG_TAIL_BYTES = 4u * 1024u * 1024u;
// Hand-wrap width for the path in the notice. The dialog's Text is 284 px of
// small font and OpenXcom's word wrap only breaks at spaces - a filesystem path
// has none, so an unwrapped one renders clipped and the player cannot find the
// file we just asked them to send.
const size_t DESYNC_PATH_WRAP = 44;

/// "20260803-141530". CrossPlatform::now() is dd-MM-yyyy_HH-mm-ss, which does not
/// sort; a folder of reports wants the sortable form.
std::string crashTimeString(const char* format)
{
	std::time_t t = std::time(0);
	std::tm local;
	std::memset(&local, 0, sizeof(local));
	if (const std::tm* p = std::localtime(&t)) local = *p;
	char buf[40];
	std::memset(buf, 0, sizeof(buf));
	if (std::strftime(buf, sizeof(buf), format, &local) == 0) return "unknown";
	return buf;
}

const char* desyncPlatform()
{
#ifdef _WIN64
	return "Windows 64 bit";
#elif defined(_WIN32)
	return "Windows 32 bit";
#elif defined(__APPLE__)
	return "OSX";
#elif defined(__ANDROID_API__)
	return "Android";
#elif defined(__linux__)
	return "Linux";
#else
	return "Unix-like";
#endif
}

/// Raw byte read, tail-capped, never throwing. CrossPlatform::readFile is wrong
/// here twice over: it opens in TEXT mode (which mangles a save's bytes on
/// Windows) and it THROWS on a missing file - a missing member has to degrade to
/// a smaller bundle, never to an exception raised inside a diagnostic.
bool readTailBinary(const std::string& path, size_t maxBytes, std::string& out)
{
	out.clear();
	SDL_RWops* rw = SDL_RWFromFile(path.c_str(), "rb");
	if (!rw) return false;
	bool ok = false;
	const int end = SDL_RWseek(rw, 0, SEEK_END);
	if (end >= 0)
	{
		const size_t total = (size_t)end;
		size_t from = 0, want = total;
		if (maxBytes != 0 && total > maxBytes)
		{
			from = total - maxBytes;
			want = maxBytes;
		}
		if (SDL_RWseek(rw, (int)from, SEEK_SET) >= 0)
		{
			if (want == 0)
			{
				ok = true;
			}
			else
			{
				out.assign(want, '\0');
				ok = (SDL_RWread(rw, &out[0], 1, (int)want) == (int)want);
			}
		}
	}
	SDL_RWclose(rw);
	if (!ok) out.clear();
	return ok;
}

/// Break a path onto dialog-sized lines, cutting after a directory separator
/// where one is in reach and mid-token where none is.
std::string wrapPathForDialog(const std::string& path)
{
	std::string out;
	size_t start = 0;
	while (path.size() - start > DESYNC_PATH_WRAP)
	{
		size_t cut = path.find_last_of("/\\", start + DESYNC_PATH_WRAP - 1);
		if (cut == std::string::npos || cut <= start) cut = start + DESYNC_PATH_WRAP - 1;
		if (!out.empty()) out += '\n';
		out.append(path, start, cut - start + 1);
		start = cut + 1;
	}
	if (start < path.size())
	{
		if (!out.empty()) out += '\n';
		out.append(path, start, path.size() - start);
	}
	return out.empty() ? path : out;
}

/// Percent-encode a string for use as a URL query value (RFC 3986 unreserved raw).
std::string desyncUrlEncode(const std::string& s)
{
	static const char* hex = "0123456789ABCDEF";
	std::string out;
	out.reserve(s.size() * 3);
	for (unsigned char c : s)
	{
		if ((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
			(c >= '0' && c <= '9') || c == '-' || c == '_' || c == '.' || c == '~')
			out += (char)c;
		else { out += '%'; out += hex[c >> 4]; out += hex[c & 0xF]; }
	}
	return out;
}

/// the crash bundle's system-info json. Mirrors buildDesyncInfo's build +
/// mods block (the same json builder), plus the marker echo
/// (crash timestamp, exception code, the version recorded AT crash time, and the
/// dump/log the crash wrote). 'build.version' is the version NOW; 'crash.crash_version'
/// is the version the crash was written under - normally identical, but distinct if
/// the player updated between the crash and the next launch.
std::string buildCrashInfo(Game* game, const std::string& source, const std::string& dump,
						   const std::string& log, const std::string& version,
						   const std::string& exception, const std::string& timestamp)
{
	(void)game;
	Json::Value root;
	root["schema"] = 1;
	root["report"] = "crash";
	root["source"] = source; // "crashdump-marker" (classic) or "veh-crashlog" (issue #124)
	root["generated"] = crashTimeString("%Y-%m-%d %H:%M:%S");

	Json::Value c;
	c["timestamp"] = timestamp;
	c["exception"] = exception;
	c["crash_version"] = version;
	c["dump"] = dump;
	c["log"] = log;
	root["crash"] = c;

	Json::Value v;
	v["version"] = std::string(OPENXCOM_VERSION_SHORT) + OPENXCOM_VERSION_GIT;
	v["engine"] = OPENXCOM_VERSION_ENGINE;
	v["oxce"] = OPENXCOM_VERSION_OXCE;
	v["platform"] = desyncPlatform();
	root["build"] = v;

	Json::Value mods(Json::arrayValue);
	for (const ModInfo* mi : Options::getActiveMods())
	{
		if (mi) mods.append(mi->getId() + " ver: " + mi->getVersion());
	}
	root["mods"] = mods;
	return root.toStyledString();
}

/// parse + validate the crash marker. Read through readTailBinary (the
/// UTF-8-safe SDL reader, not std::ifstream) so a user folder with non-ASCII in
/// the path still opens on Windows. Never throws; a missing/corrupt marker returns
/// false and the caller deletes it.
bool parseCrashMarker(const std::string& markerPath, std::string& dump, std::string& log,
					  std::string& version, std::string& exception, std::string& timestamp)
{
	std::string blob;
	if (!readTailBinary(markerPath, 0, blob) || blob.empty()) return false;
	std::istringstream ss(blob);
	Json::CharReaderBuilder b;
	Json::Value root;
	std::string errs;
	if (!Json::parseFromStream(b, ss, &root, &errs) || !root.isObject()) return false;
	dump      = root.get("dump", "").asString();
	log       = root.get("log", "").asString();
	version   = root.get("version", "").asString();
	exception = root.get("exception", "").asString();
	timestamp = root.get("timestamp", "").asString();
	return true;
}

// ---- dual-source discovery: crashlogs scan + seen-ledger --------------------
// The crashed process ALREADY writes crash_<ts>_<seq>.{dmp,log} + mod list to
// <exe>/crashlogs (issue #124 CrashHandler VEH - the robust catch-all that fires
// even when the fault unwinds through a noexcept frame into std::terminate and so
// NEVER reaches CrossPlatform::crashDump). The next launch therefore discovers a
// crash from EITHER the crashDump marker (classic, rich) OR an unseen crashlogs
// entry (the VEH path). A per-user-folder seen-ledger (crash-seen.json) dedups:
// BUNDLE and NEVER mark seen, NOT NOW leaves it unseen. First-run rule (least-
// surprising): the ledger stamps its creation time as a baseline and only entries
// NEWER than it are ever offered, so pre-existing / pre-feature crashlogs never
// retro-nag.

std::string crashSeenLedgerPath() { return Options::getUserFolder() + "crash-seen.json"; }

// Load the ledger; CREATE it (baseline = now, empty seen) if absent. Never throws.
void loadOrCreateSeenLedger(time_t& baseline, std::set<std::string>& seen)
{
	baseline = 0; seen.clear();
	std::string blob;
	if (readTailBinary(crashSeenLedgerPath(), 0, blob) && !blob.empty())
	{
		std::istringstream ss(blob);
		Json::CharReaderBuilder b; Json::Value root; std::string errs;
		if (Json::parseFromStream(b, ss, &root, &errs) && root.isObject())
		{
			baseline = (time_t)root.get("baseline", 0).asInt64();
			const Json::Value& arr = root["seen"];
			if (arr.isArray())
				for (const auto& v : arr) seen.insert(v.asString());
			return;
		}
	}
	baseline = time(nullptr); // fresh: pre-existing crashlogs (older) are never offered
	Json::Value root;
	root["baseline"] = Json::Value::Int64((int64_t)baseline);
	root["seen"] = Json::Value(Json::arrayValue);
	CrossPlatform::writeFile(crashSeenLedgerPath(), root.toStyledString());
}

void crashlogAddSeen(const std::string& dmpBasename)
{
	if (dmpBasename.empty()) return;
	time_t baseline; std::set<std::string> seen;
	loadOrCreateSeenLedger(baseline, seen);
	seen.insert(dmpBasename);
	Json::Value root;
	root["baseline"] = Json::Value::Int64((int64_t)baseline);
	Json::Value arr(Json::arrayValue);
	for (const auto& s : seen) arr.append(s);
	root["seen"] = arr;
	CrossPlatform::writeFile(crashSeenLedgerPath(), root.toStyledString());
}

std::string crashBasename(const std::string& path)
{
	size_t s = path.find_last_of("/\\");
	return (s == std::string::npos) ? path : path.substr(s + 1);
}

// The shared seq token = the last '_'-delimited field before the extension (the
// .dmp and its .log share it; they differ only in the ms part of the timestamp).
std::string crashlogSeq(const std::string& name)
{
	size_t dot = name.find_last_of('.');
	std::string stem = (dot == std::string::npos) ? name : name.substr(0, dot);
	size_t us = stem.find_last_of('_');
	return (us == std::string::npos) ? std::string() : stem.substr(us + 1);
}

// crash_YYYYMMDD_HHMMSS_mmm_seq.ext -> "YYYYMMDD_HHMMSS" (zip name / info ts).
std::string crashlogTsToken(const std::string& name)
{
	static const std::string pre = "crash_";
	if (name.compare(0, pre.size(), pre) != 0 || name.size() < pre.size() + 15) return std::string();
	return name.substr(pre.size(), 15);
}

// Newest crash_*.dmp basename by mtime (or empty) - used to dedup the marker's pair.
std::string crashlogNewestDmp()
{
	const std::string dir = ::CrashHandler::logDirectory();
	if (dir.empty()) return std::string();
	std::string best; time_t bestT = 0;
	for (const auto& e : CrossPlatform::getFolderContents(dir, "dmp"))
	{
		if (std::get<1>(e)) continue;
		const std::string& nm = std::get<0>(e);
		if (nm.compare(0, 6, "crash_") != 0) continue;
		time_t tm = std::get<2>(e);
		if (best.empty() || tm > bestT) { best = nm; bestT = tm; }
	}
	return best;
}

// Newest crash_*.dmp with mtime > baseline and basename NOT in seen; pair its .log
// by matching seq + nearest mtime. Fills paths + ts token. Never throws here.
bool findNewestUnseenCrashlog(std::string& dmpPath, std::string& logPath, std::string& tsToken)
{
	dmpPath.clear(); logPath.clear(); tsToken.clear();
	const std::string dir = ::CrashHandler::logDirectory();
	if (dir.empty()) return false;
	time_t baseline; std::set<std::string> seen;
	loadOrCreateSeenLedger(baseline, seen);
	std::string bestName; time_t bestT = 0;
	for (const auto& e : CrossPlatform::getFolderContents(dir, "dmp"))
	{
		if (std::get<1>(e)) continue;
		const std::string& nm = std::get<0>(e);
		if (nm.compare(0, 6, "crash_") != 0) continue;
		time_t tm = std::get<2>(e);
		if (tm <= baseline) continue;   // first-run / pre-feature guard
		if (seen.count(nm)) continue;   // already handled
		if (bestName.empty() || tm > bestT) { bestName = nm; bestT = tm; }
	}
	if (bestName.empty()) return false;
	dmpPath = dir + "/" + bestName;
	tsToken = crashlogTsToken(bestName);
	const std::string seqWanted = crashlogSeq(bestName);
	std::string bestLog; time_t bestDiff = 0; bool haveLog = false;
	for (const auto& e : CrossPlatform::getFolderContents(dir, "log"))
	{
		if (std::get<1>(e)) continue;
		const std::string& nm = std::get<0>(e);
		if (nm.compare(0, 6, "crash_") != 0) continue;
		if (crashlogSeq(nm) != seqWanted) continue;
		time_t tm = std::get<2>(e);
		time_t diff = (tm > bestT) ? (tm - bestT) : (bestT - tm);
		if (!haveLog || diff < bestDiff) { bestLog = nm; bestDiff = diff; haveLog = true; }
	}
	if (haveLog) logPath = dir + "/" + bestLog;
	return true;
}

// Shared tail of both bundle paths: write the zip + raise the I4 result notice.
bool emitCrashBundle(Game* game, const std::vector<std::pair<std::string, std::string> >& members,
					 const std::string& tsFile, const std::string& exception,
					 const std::string& version, const std::string& timestamp)
{
	const std::string dir = Options::getUserFolder() + "crash-reports/";
	if (!CrossPlatform::folderExists(dir)) CrossPlatform::createFolder(dir);
	if (!CrossPlatform::folderExists(dir))
	{
		Log(LOG_ERROR) << "[COOP] crash report: cannot create " << dir;
		return false;
	}
	const std::string tsF = tsFile.empty() ? crashTimeString("%Y%m%d-%H%M%S") : tsFile;
	const std::string path = dir + "crash-" + tsF + ".zip";
	if (!writeZipArchive(path, members))
	{
		Log(LOG_ERROR) << "[COOP] crash report: failed to write " << path;
		return false;
	}
	Log(LOG_INFO) << "[COOP] crash report written to " << path
				  << " (" << (int)members.size() << " members)";
	if (game && game->getLanguage())
	{
		const std::string issueBase =
			"https://github.com/OpenXcom-Coop/OpenXcom-Coop-Mod/issues/new";
		const std::string title = "[coop crash] " + exception + " " + version;
		std::ostringstream body;
		body << "OpenXcom crashed and the next launch bundled the details.\n\n";
		body << "  version:   " << version << "\n";
		body << "  exception: " << exception << "\n";
		body << "  timestamp: " << timestamp << "\n\n";
		body << "Please ATTACH the crash zip (do not paste it) to this issue:\n";
		body << "  " << path << "\n\n";
		body << "(auto-generated by the co-op crash reporter; dump, log + system info are in the zip)\n";
		const std::string reportUrl = issueBase + "?title=" + desyncUrlEncode(title) +
			"&body=" + desyncUrlEncode(body.str());
		game->pushState(new CoopDesyncNoticeState(
			game->getLanguage()->getString("STR_COOP_CRASH_REPORT_SAVED").arg(wrapPathForDialog(path)),
			game->getLanguage()->getString("STR_COOP_CRASH_REPORT_HEADLINE"),
			path, reportUrl));
	}
	return true;
}

} // namespace

// ---- next-launch crash reporter --------------------------------------
// The dying process wrote only a marker (CrossPlatform::crashDump). These run at
// the NEXT launch from the main-menu altitude. Best-effort by contract: every
// path logs and continues, and only a SUCCESSFUL bundle deletes the marker.

void deleteCrashMarkerFile(const std::string& markerPath)
{
	try
	{
		if (!markerPath.empty() && CrossPlatform::fileExists(markerPath))
			CrossPlatform::deleteFile(markerPath);
	}
	catch (...) {}
}

void markCrashlogSeenPath(const std::string& dmpPath)
{
	try { crashlogAddSeen(crashBasename(dmpPath)); } catch (...) {}
}

// NEVER on the classic MARKER: delete it AND mark its paired VEH crashlog (the
// newest crash_*.dmp, written microseconds earlier by the first-chance handler)
// seen, so the scan does not re-offer the same crash next launch. Single-crash-
// since-launch assumption; a rare stale-marker + newer-VEH-crash edge could
// suppress one prompt - acceptable.
void declineCrashMarker(const std::string& markerPath)
{
	try
	{
		deleteCrashMarkerFile(markerPath);
		crashlogAddSeen(crashlogNewestDmp());
	}
	catch (...) {}
}

bool bundleCrashReportFromMarker(Game* game, const std::string& markerPath)
{
	try
	{
		std::string dump, log, version, exception, timestamp;
		if (!parseCrashMarker(markerPath, dump, log, version, exception, timestamp))
		{
			Log(LOG_WARNING) << "[COOP] crash report: marker unreadable, ignoring: " << markerPath;
			deleteCrashMarkerFile(markerPath);
			return false;
		}
		if (dump.empty() || !CrossPlatform::fileExists(dump) ||
			log.empty()  || !CrossPlatform::fileExists(log))
		{
			Log(LOG_WARNING) << "[COOP] crash report: marker names missing files, ignoring";
			deleteCrashMarkerFile(markerPath);
			return false;
		}
		std::vector<std::pair<std::string, std::string> > members;
		members.push_back(std::make_pair(std::string("crash-info.json"),
			buildCrashInfo(game, "crashdump-marker", dump, log, version, exception, timestamp)));
		std::string blob;
		if (readTailBinary(dump, 0, blob))
			members.push_back(std::make_pair(std::string("crash.dmp"), blob));
		else Log(LOG_WARNING) << "[COOP] crash report: could not read dump " << dump;
		// One persistent openxcom.log (never truncated) carries the crash's own trace.
		if (readTailBinary(log, DESYNC_LOG_TAIL_BYTES, blob))
			members.push_back(std::make_pair(std::string("openxcom.log"), blob));
		else Log(LOG_WARNING) << "[COOP] crash report: could not read log " << log;

		const std::string tsFile = timestamp.empty() ? std::string() : timestamp;
		if (!emitCrashBundle(game, members, tsFile, exception, version, timestamp))
			return false; // keep the marker; retry next launch
		deleteCrashMarkerFile(markerPath);   // SUCCESS: the marker is spent
		crashlogAddSeen(crashlogNewestDmp()); // and dedup its paired VEH crashlog
		return true;
	}
	catch (const std::exception& e) { Log(LOG_ERROR) << "[COOP] crash report failed: " << e.what(); }
	catch (...) { Log(LOG_ERROR) << "[COOP] crash report failed"; }
	return false;
}

// BUNDLE on a VEH crashlog (issue #124): the crash artifacts already exist on
// disk - zip the dump + the #124 crash-log (stack + mod list) + the openxcom.log
// tail + a system-info json (source=veh-crashlog, ts from the filename; the exact
// exception code is inside crash-log.txt). Marks the .dmp basename seen on success.
bool bundleCrashReportFromCrashlog(Game* game, const std::string& dmpPath, const std::string& logPath)
{
	try
	{
		if (dmpPath.empty() || !CrossPlatform::fileExists(dmpPath))
		{
			Log(LOG_WARNING) << "[COOP] crash report: crashlog dump gone, marking seen: " << dmpPath;
			markCrashlogSeenPath(dmpPath);
			return false;
		}
		const std::string version = std::string(OPENXCOM_VERSION_SHORT) + OPENXCOM_VERSION_GIT;
		const std::string exception = "(see crash-log.txt)";
		const std::string tsToken = crashlogTsToken(crashBasename(dmpPath));
		std::vector<std::pair<std::string, std::string> > members;
		members.push_back(std::make_pair(std::string("crash-info.json"),
			buildCrashInfo(game, "veh-crashlog", dmpPath, logPath, version, exception, tsToken)));
		std::string blob;
		if (readTailBinary(dmpPath, 0, blob))
			members.push_back(std::make_pair(std::string("crash.dmp"), blob));
		else Log(LOG_WARNING) << "[COOP] crash report: could not read dump " << dmpPath;
		if (!logPath.empty() && readTailBinary(logPath, DESYNC_LOG_TAIL_BYTES, blob))
			members.push_back(std::make_pair(std::string("crash-log.txt"), blob));
		if (readTailBinary(CrossPlatform::getLogFileName(), DESYNC_LOG_TAIL_BYTES, blob))
			members.push_back(std::make_pair(std::string("openxcom.log"), blob));

		if (!emitCrashBundle(game, members, tsToken, exception, version, tsToken))
			return false; // leave it unseen -> retry next launch
		markCrashlogSeenPath(dmpPath);
		return true;
	}
	catch (const std::exception& e) { Log(LOG_ERROR) << "[COOP] crash report failed: " << e.what(); }
	catch (...) { Log(LOG_ERROR) << "[COOP] crash report failed"; }
	return false;
}

void maybeReportPreviousCrash(Game* game)
{
	try
	{
		// Source 1 (preferred, rich): the classic crashDump marker.
		const std::string markerPath = Options::getUserFolder() + "crash-pending.json";
		if (CrossPlatform::fileExists(markerPath))
		{
			std::string dump, log, version, exception, timestamp;
			if (!parseCrashMarker(markerPath, dump, log, version, exception, timestamp))
			{
				Log(LOG_WARNING) << "[COOP] crash marker unreadable, deleting: " << markerPath;
				deleteCrashMarkerFile(markerPath); // then fall through to the crashlogs scan
			}
			else if (!dump.empty() && CrossPlatform::fileExists(dump) &&
					 !log.empty()  && CrossPlatform::fileExists(log))
			{
				if (!game || !game->getLanguage()) return; // no UI; leave the marker
				Log(LOG_INFO) << "[COOP] previous crash detected (marker, " << exception << ")";
				game->pushState(new CoopCrashPromptState(
					game->getLanguage()->getString("STR_COOP_CRASH_REPORT_PROMPT"),
					game->getLanguage()->getString("STR_COOP_CRASH_REPORT_HEADLINE"),
					markerPath, std::string(), std::string()));
				return;
			}
			else
			{
				Log(LOG_INFO) << "[COOP] crash marker names missing files, deleting";
				deleteCrashMarkerFile(markerPath); // fall through to the scan
			}
		}
		// Source 2 (robust catch-all): an unseen issue-#124 VEH crashlog. The
		// ledger's baseline keeps this O(small) and never retro-nags about old ones.
		std::string dmpPath, logPath, tsToken;
		if (findNewestUnseenCrashlog(dmpPath, logPath, tsToken))
		{
			if (!game || !game->getLanguage()) return;
			Log(LOG_INFO) << "[COOP] previous crash detected (crashlog " << dmpPath << ")";
			game->pushState(new CoopCrashPromptState(
				game->getLanguage()->getString("STR_COOP_CRASH_REPORT_PROMPT"),
				game->getLanguage()->getString("STR_COOP_CRASH_REPORT_HEADLINE"),
				std::string(), dmpPath, logPath));
		}
	}
	catch (const std::exception& e)
	{
		Log(LOG_ERROR) << "[COOP] crash reporter startup check failed: " << e.what();
	}
	catch (...)
	{
		Log(LOG_ERROR) << "[COOP] crash reporter startup check failed";
	}
}

} // namespace SharedEcon
} // namespace OpenXcom
