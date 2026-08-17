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

#include <algorithm>
#include <atomic>
#include <chrono>
#include <deque>
#include <map>
#include <mutex>
#include <set>
#include <sstream>
#include <string_view>
#include <unordered_map>
#include <tuple>
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
#include "../Savegame/ResearchProject.h"
#include "../Savegame/Production.h"
#include "../Savegame/Ufo.h"
#include "../Savegame/MissionSite.h"
#include "../Savegame/AlienBase.h"
#include "../Savegame/Waypoint.h"
#include "../Savegame/Target.h"
#include "../Savegame/AlienMission.h"
#include "../Savegame/CraftWeapon.h"
#include "../Savegame/Country.h"
#include "../Savegame/WeightedOptions.h"
#include "../Savegame/SavedBattleGame.h"
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

#include <cmath>
#include "../Basescape/BaseView.h"
#include "../Basescape/CraftWeaponsState.h" // issue #121: shared craft-weapon capacity gate
#include "../Geoscape/GeoscapeState.h"
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
#include "../Geoscape/AlienBaseState.h"
#include "../Geoscape/BaseDestroyedState.h"
#include "../Savegame/AlienBase.h"
#include "../Mod/RuleEvent.h"
#include "../Menu/ErrorMessageState.h"

#include "connectionTCP.h"
#include "CoopState.h"
#include "CrashHandler.h"

// Desync auto-report bundle. miniz is already vendored (libs/miniz) and already
// compiled into both build systems for FileMap's zip-mod reader, so the zip
// WRITER costs nothing new. MINIZ_NO_STDIO matches how CMake compiles miniz.c
// (src/CMakeLists.txt) - without it this header would offer the file-based
// writer APIs that exist only in the MSVC object, i.e. a Windows-only feature
// that fails to LINK on the Linux AppImage. The heap writer is guard-free on
// both, so everything below builds an archive in memory and writes the bytes
// out through CrossPlatform's binary writeFile().
#include "../Engine/CrossPlatform.h"
#include "../version.h"

#include <cstring>
#include <ctime>

#define MINIZ_NO_STDIO
#include "../../libs/miniz/miniz.h"

namespace OpenXcom
{
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
	Json::Value payload;
	bool remote = false;
};

std::mutex g_mx;                     // guards the four queues below
std::deque<PendingCmd>  g_cmdQ;      // host:      to validate+apply+broadcast
std::deque<Json::Value> g_applyQ;    // replica:   shared_apply to apply
std::deque<std::string> g_failQ;     // initiator: shared_fail reasons to surface
int g_resyncServeQ = 0;              // host:      pending shared_resync_requests

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
// replica, so host and every replica hold the same base list in the same order;
// the index is a stable shared key. _coop_base_id is 0/unset for a SHARED
// campaign's own real bases, so it is NOT usable. Base add/remove also rides
// shared_apply (J07), keeping the ordering in lock-step.
Base* resolveBase(Game* game, int baseId)
{
	if (!game || !game->getSavedGame()) return nullptr;
	auto* bases = game->getSavedGame()->getBases();
	if (baseId < 0 || baseId >= (int)bases->size()) return nullptr;
	return (*bases)[baseId];
}

void setLastFail(const std::string& reason)
{
	std::lock_guard<std::mutex> lk(g_failMx);
	g_lastFail = reason;
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
			// PRD-J05: hired soldiers spend shared funds; the purchaser owns them
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
			t->setItems(r, qty);
			base->getTransfers()->push_back(t);
			break;
		}
		case TRANSFER_SCIENTIST:
		{
			Transfer* t = new Transfer(mod->getPersonnelTime());
			t->setScientists(qty);
			base->getTransfers()->push_back(t);
			break;
		}
		case TRANSFER_ENGINEER:
		{
			Transfer* t = new Transfer(mod->getPersonnelTime());
			t->setEngineers(qty);
			base->getTransfers()->push_back(t);
			break;
		}
		case TRANSFER_CRAFT:
		{
			RuleCraft* r = mod->getCraft(rule, false);
			if (!r) break;
			if (r->getMonthlyBuyLimit() > 0) limitLog[r->getType()] += qty;
			for (int c = 0; c < qty; ++c)
			{
				Transfer* t = new Transfer(r->getTransferTime());
				// getId() advances the per-type counter identically on host and
				// replica (same start + same shared_apply on both), so no id needs
				// to travel in the packet and the counters stay in lock-step.
				Craft* craft = new Craft(r, base, save->getId(r->getType()));
				craft->initFixedWeapons(mod);
				craft->setStatus("STR_REFUELLING");
				t->setCraft(craft);
				base->getTransfers()->push_back(t);
			}
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
					soldier->setOwnerPlayerId(seat); // PRD-J05: purchaser owns the hire
					Transfer* t = new Transfer(time);
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
					soldier->setOwnerPlayerId(seat); // belt-and-braces (also in YAML)
					Transfer* t = new Transfer(time);
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
			if (base->getStorageItems()->getItem(r) < qty)
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

	// ORDER (items -> soldiers -> crafts -> scientists -> engineers) is fixed and
	// identical on host and replica, so both worlds mutate the same way.
	const Json::Value& items = payload["items"];
	if (items.isArray())
		for (const auto& it : items)
		{
			int qty = it.get("qty", 0).asInt();
			RuleItem* r = mod->getItem(it.get("rule", "").asString(), false);
			if (r && qty > 0) base->getStorageItems()->removeItem(r, qty);
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

	const Json::Value& crafts = payload["crafts"];
	if (crafts.isArray())
		for (const auto& jc : crafts)
		{
			Craft* c = findCraft(fromBase, jc.get("id", -1).asInt(), jc.get("type", "").asString());
			if (!c) { failReason = "craft not transferable"; return false; }
			total += craftCost;
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
	if (incomingPersonnel > 0
		&& toBase->getAvailableQuarters() - toBase->getUsedQuarters() < incomingPersonnel)
		{ failReason = "STR_NO_FREE_ACCOMODATION"; return false; }

	cost = total; // positive debit
	return true;
}

void transferApply(Game* game, Json::Value& payload, Base* fromBase, int /*seat*/)
{
	if (!fromBase) return;
	Mod* mod = game->getMod();
	if (!mod) return;
	Base* toBase = resolveBase(game, payload.get("toBaseId", -1).asInt());
	if (!toBase) return;

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
			t->setItems(r, qty);
			toBase->getTransfers()->push_back(t);
		}

	const Json::Value& soldiers = payload["soldiers"];
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
					// Ownership unchanged by a transfer (PRD-J05).
					Transfer* t = new Transfer(time);
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
					t->setSoldier(s);
					toBase->getTransfers()->push_back(t);
					it = fromBase->getSoldiers()->erase(it);
				}
				else ++it;
			}
			fromBase->removeCraft(craft, false);
			Transfer* t = new Transfer(time);
			t->setCraft(craft);
			toBase->getTransfers()->push_back(t);
		}

	int sci = payload.get("scientists", 0).asInt();
	int eng = payload.get("engineers", 0).asInt();
	if (sci > 0)
	{
		fromBase->setScientists(fromBase->getScientists() - sci);
		Transfer* t = new Transfer(time);
		t->setScientists(sci);
		toBase->getTransfers()->push_back(t);
	}
	if (eng > 0)
	{
		fromBase->setEngineers(fromBase->getEngineers() - eng);
		Transfer* t = new Transfer(time);
		t->setEngineers(eng);
		toBase->getTransfers()->push_back(t);
	}
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
		base->getStorageItems()->removeItem(rule->getNeededItem(), 1);
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

void manStartApply(Game* game, Json::Value& payload, Base* base, int /*seat*/)
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
bool sackValidate(Game* /*game*/, const Json::Value& payload, Base* base, int /*seat*/,
                  int64_t& cost, std::string& failReason)
{
	if (!base) { failReason = "base not found"; return false; }
	int id = payload.get("soldierId", -1).asInt();
	for (auto* s : *base->getSoldiers())
		if (s->getId() == id) { cost = 0; return true; }
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

// soldier_rename payload: { soldierId, name }. Playtest B3: soldier renames were
// local-only; in SHARED they ride the shared_cmd like base_rename (host applies +
// broadcasts, last-write-wins). ANY player may rename ANY soldier (shared roster,
// consistent with sack). The soldier is looked up by id at the command's base.
bool soldierRenameValidate(Game* /*game*/, const Json::Value& payload, Base* base, int /*seat*/,
                           int64_t& cost, std::string& failReason)
{
	if (!base) { failReason = "base not found"; return false; }
	int id = payload.get("soldierId", -1).asInt();
	for (auto* s : *base->getSoldiers())
		if (s->getId() == id) { cost = 0; return true; }
	failReason = "soldier not found";
	return false;
}
void soldierRenameApply(Game* /*game*/, Json::Value& payload, Base* base, int /*seat*/)
{
	if (!base) return;
	int id = payload.get("soldierId", -1).asInt();
	for (auto* s : *base->getSoldiers())
		if (s->getId() == id) { s->setName(payload.get("name", s->getName()).asString()); break; }
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
void soldierGiftApply(Game* /*game*/, Json::Value& payload, Base* base, int /*seat*/)
{
	if (!base) return;
	int id = payload.get("soldierId", -1).asInt();
	int newOwner = payload.get("newOwner", 0).asInt();
	for (auto* s : *base->getSoldiers())
		if (s->getId() == id) { s->setOwnerPlayerId(newOwner); s->setCoop(newOwner); break; }
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

void baseNewApply(Game* game, Json::Value& payload, Base* /*base*/, int /*seat*/)
{
	SavedGame* save = game->getSavedGame();
	Mod* mod = game->getMod();
	if (!save || !mod) return;

	Base* nb = new Base(mod); // ctor random-mints _coop_base_id
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
	if (!base) return;
	SavedGame* save = game->getSavedGame();
	if (!save) return;
	std::string name = payload.get("name", base->getName()).asString();
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

// Last wound-recovery value the host broadcast per soldier id, so day_tick only
// carries CHANGED soldiers (process-global; compare-and-set makes stale entries
// self-correct on the next change).
std::unordered_map<int, int> g_soldierRecovery;

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
Soldier* findSoldierAtBase(Base* base, int id)
{
	if (!base) return nullptr;
	for (auto* s : *base->getSoldiers())
		if (s->getId() == id) return s;
	return nullptr;
}

bool craftAssignValidate(Game* game, const Json::Value& payload, Base* base, int /*seat*/,
                         int64_t& cost, std::string& failReason)
{
	cost = 0; // no funds effect; broadcast still carries authoritative getFunds()
	if (!base) { failReason = "base not found"; return false; }
	Craft* craft = resolveOrderCraft(game, payload, base);
	if (!craft) { failReason = "craft not found"; return false; }
	Soldier* s = findSoldierAtBase(base, payload.get("soldierId", -1).asInt());
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
	Soldier* s = findSoldierAtBase(base, payload.get("soldierId", -1).asInt());
	if (!craft || !s) return;
	const bool onOff = payload.get("onOff", false).asBool();
	const bool newBattle = game->getSavedGame()->getMonthsPassed() == -1;
	if (onOff)
		s->setCraftAndMoveEquipment(craft, base, newBattle, true);
	else if (s->getCraft() == craft)
		s->setCraftAndMoveEquipment(0, base, newBattle);
}

// ---- PRD-J09 GAP-5: shared-world craft equipment loadout ---------------------
// Equipping a craft at the BASE screen (CraftEquipmentState) moves items between
// the shared base stores and the craft. Those base stores are host-authoritative
// (they are exactly what the GAP-4 checksum sums), so a replica must never mutate
// them locally - it routes the move through this command instead. payload:
//   { craftId, craftType, item, count }   baseId = the craft's home-base index.
// count = the ABSOLUTE desired quantity of `item` loaded on the craft, so host
// and replica converge regardless of arrival order (the J08/J09 last-write-wins
// idiom). Items only; vehicles/ammo are deferred (like craft_assign's vehicle
// variant - CraftEquipmentState still routes non-vehicle items only).
bool craftEquipValidate(Game* game, const Json::Value& payload, Base* base, int /*seat*/,
                        int64_t& cost, std::string& failReason)
{
	cost = 0; // no funds effect; broadcast still carries authoritative getFunds()
	if (!base) { failReason = "base not found"; return false; }
	if (!resolveOrderCraft(game, payload, base)) { failReason = "craft not found"; return false; }
	const RuleItem* item = game->getMod()->getItem(payload.get("item", "").asString(), false);
	if (!item) { failReason = "unknown item"; return false; }
	if (item->getVehicleUnit()) { failReason = "vehicles not routed"; return false; }
	return true;
}

void craftEquipApply(Game* game, Json::Value& payload, Base* base, int /*seat*/)
{
	if (!base) return;
	Craft* craft = resolveOrderCraft(game, payload, base);
	const RuleItem* item = game->getMod()->getItem(payload.get("item", "").asString(), false);
	if (!craft || !item || item->getVehicleUnit()) return;

	ItemContainer* craftItems = craft->getItems();
	ItemContainer* store = base->getStorageItems();
	int current = craftItems->getItem(item);
	int target = payload.get("count", 0).asInt();
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

// soldier_armor payload: { soldierId, armor }. baseId = the soldier's base index.
// End-state = which armor the soldier wears (identity swap, last-write-wins - the
// J09 "model the payload to the state, not literally a count" adaptation). Mirrors
// SoldierArmorState / CraftArmorState: return the old armor's store item + consume
// the new one against the shared stores.
bool soldierArmorValidate(Game* game, const Json::Value& payload, Base* base, int /*seat*/,
                          int64_t& cost, std::string& failReason)
{
	cost = 0;
	if (!base) { failReason = "base not found"; return false; }
	Soldier* s = findSoldier(base, payload.get("soldierId", -1).asInt());
	if (!s) { failReason = "soldier not found"; return false; }
	Armor* next = game->getMod()->getArmor(payload.get("armor", "").asString(), false);
	if (!next) { failReason = "unknown armor"; return false; }

	// issue #121: re-run the client's craft-space gate (SoldierArmorState::lstArmorClick)
	// against the host-authoritative world. If the soldier rides a craft, a larger armor
	// must still fit; the client gate can pass on a stale replica view, so the host is the
	// backstop that keeps a shared craft from being pushed over capacity.
	Craft* craft = s->getCraft();
	if (craft && !craft->validateArmorChange(s->getArmor()->getSize(), next->getSize()))
	{ failReason = "STR_NOT_ENOUGH_CRAFT_SPACE"; return false; }
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
	if (save) save->setLastSelectedArmor(next->getType());
}

// PRD-DF01: df_open applier (REPLICA only). The host publishes the FULL dogfight
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
	int ufoId = payload.get("ufoId", -1).asInt();
	std::string craftType = payload.get("craftType", "").asString();
	std::string action = payload.get("action", "").asString();
	int arg = payload.get("arg", -1).asInt();
	if (!gs->sharedApplyDogfightCmd(craftId, ufoId, craftType, action, arg))
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
	GeoscapeState* gs = findGeoState(game);
	if (!gs) return;
	Ufo* ufo = nullptr;
	const int ufoId = payload.get("ufoId", -1).asInt();
	for (auto* u : *save->getUfos())
		if (u->getId() == ufoId) { ufo = u; break; }
	gs->popup(new BaseDestroyedState(base, ufo, true, true));
}

// alien_base_found payload: { alienBaseId }. Host-origin, replica-only apply.
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
	for (auto* ab : *save->getAlienBases())
	{
		if (ab->getId() == id)
		{
			if (!ab->isDiscovered())
				ab->setDiscovered(true);
			gs->popup(new AlienBaseState(ab, gs));
			return;
		}
	}
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
	const std::string msg = payload.get("msg", "").asString();

	std::vector<std::string> names;
	const Json::Value& jn = payload["names"];
	for (Json::ArrayIndex i = 0; i < jn.size(); ++i) names.push_back(jn[i].asString());

	// `base` is routed by baseIdx already; fall back to the first base for dialogs that
	// need one but were raised without a meaningful index.
	if (!base && !game->getSavedGame()->getBases()->empty())
		base = game->getSavedGame()->getBases()->front();

	if (cls == "UfoLostState")
	{
		gs->popup(new UfoLostState(msg));
	}
	else if (cls == "CraftErrorState")
	{
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
				row.name = jr[i].get("name", "").asString();
				row.qty = jr[i].get("qty", 0).asInt();
				row.base = jr[i].get("base", "").asString();
				row.baseIdx = jr[i].get("baseIdx", -1).asInt();
				row.ownerSeat = jr[i].get("ownerSeat", -1).asInt();
				rows.push_back(row);
			}
			gs->popup(new ItemsArrivingState(gs, rows));
		}
	}
	else if (cls == "ResearchRequiredState")
	{
		if (RuleItem* it = mod->getItem(msg, false)) gs->popup(new ResearchRequiredState(it));
	}
	else if (cls == "GeoscapeEventState")
	{
		if (const RuleEvent* ev = mod->getEvent(msg, false)) gs->popup(new GeoscapeEventState(*ev));
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
		if (base)
		{
			for (Json::ArrayIndex i = 0; i < ids.size(); ++i)
				for (auto* s : *base->getSoldiers())
					if (s->getId() == ids[i].asInt()) v.push_back(s);
			if (!v.empty())
				gs->popup(new TrainingFinishedState(base, v, payload.get("flag", false).asBool()));
		}
	}
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

	// Add the discovered topic(s). The host already selected the getOneFree
	// (RNG) and passed it as `bonus`; addFinishedResearch itself is deterministic,
	// so applying the host's exact choices keeps the replica identical.
	if (bonus)
	{
		save->addFinishedResearch(bonus, mod, base);
		if (!bonus->getLookup().empty())
			save->addFinishedResearch(mod->getResearch(bonus->getLookup(), true), mod, base);
	}
	save->addFinishedResearch(research, mod, base);
	if (!research->getLookup().empty())
		save->addFinishedResearch(mod->getResearch(research->getLookup(), true), mod, base);

	// Mirror the host popup (coop=true -> the ctor does NOT re-broadcast).
	const std::string nrName = payload.get("newResearch", "").asString();
	const RuleResearch* newResearch = nrName.empty() ? nullptr : mod->getResearch(nrName, false);
	game->pushState(new ResearchCompleteState(newResearch, bonus, research, base, true));
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
			if (gs)
				game->pushState(new ProductionCompleteState(
					base, game->getLanguage()->getString(payload.get("type", "").asString()),
					gs, PROGRESS_CONSTRUCTION));
			break;
		}
	}
}

// prod_done payload: { manufacture, units, progress, sell }.
void prodDoneApply(Game* game, Json::Value& payload, Base* base, int /*seat*/)
{
	if (connectionTCP::getHost()) return;
	if (!base) return;
	SavedGame* save = game->getSavedGame();
	Mod* mod = game->getMod();
	if (!save || !mod) return;

	const std::string mName = payload.get("manufacture", "").asString();
	int units = payload.get("units", 0).asInt();
	// GAP-6b: the host Production's SELL flag. When set, Production::step() credited
	// funds and added NOTHING to stores for the produced items; the authoritative
	// funds ride this shared_apply as usual, so the replica must skip the storage add
	// or its item count drifts ABOVE the host. The sell branch lives inside the
	// NON-craft arm of Production::step(), so a produced CRAFT is never sold - the
	// craft materialization below stays unconditional.
	bool sell = payload.get("sell", false).asBool();
	RuleManufacture* rule = mod->getManufacture(mName, false);
	if (!rule || units <= 0) return;

	// Materialize the deterministic output (items + crafts). Random/spawned-person
	// production is host-RNG and NOT reconstructed here (documented limitation);
	// the next shared_apply / checksum surfaces any resulting drift.
	if (!sell)
		for (const auto& it : rule->getProducedItems())
			base->getStorageItems()->addItem(it.first, it.second * units);
	if (const RuleCraft* craftRule = rule->getProducedCraft())
	{
		for (int c = 0; c < units; ++c)
		{
			// getId(craftType) advances the per-type counter identically to the
			// host (all craft creation rides shared_apply), so ids stay in lockstep.
			Craft* craft = new Craft(const_cast<RuleCraft*>(craftRule), base,
			                         save->getId(craftRule->getType()));
			craft->initFixedWeapons(mod);
			craft->checkup();
			base->getCrafts()->push_back(craft);
		}
	}

	// Remove the matching Production (returns its engineers to the base pool) and
	// mirror the completion popup.
	for (auto* prod : base->getProductions())
	{
		if (prod->getRules()->getName() == mName)
		{
			GeoscapeState* gs = findGeoState(game);
			if (gs)
				game->pushState(new ProductionCompleteState(
					base, game->getLanguage()->getString(mName), gs,
					(productionProgress_e)payload.get("progress", PROGRESS_COMPLETE).asInt(),
					prod));
			base->removeProduction(prod);
			break;
		}
	}
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

// day_tick payload: { soldiers:[{id,recovery}], productions:[{item,spent}],
// research:[{project,spent}] }. PRD-J06: the replica's timeXxx handlers are
// frozen, so production _timeSpent and research _spent never advance locally;
// the host broadcasts the day's progress so the "days left" / "Progress" columns
// render current on replicas. Display-only (completion is host-driven J04).
void dayTickApply(Game* game, Json::Value& payload, Base* base, int /*seat*/)
{
	if (connectionTCP::getHost()) return;
	if (!base) return;
	const Json::Value& soldiers = payload["soldiers"];
	if (soldiers.isArray())
		for (const auto& s : soldiers)
		{
			int id = s.get("id", -1).asInt();
			int recovery = s.get("recovery", 0).asInt();
			for (auto* soldier : *base->getSoldiers())
			{
				if (soldier->getId() == id)
				{
					soldier->setWoundRecovery(recovery);
					break;
				}
			}
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

// ---- Host-side command processing (main thread) ------------------------------
void rejectHostCmd(Game* game, const PendingCmd& pc, const std::string& reason)
{
	++g_failN;
	setLastFail(reason);
	if (pc.remote)
	{
		Json::Value fail;
		fail["state"] = "shared_fail";
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

	Base* base = resolveBase(game, pc.baseId);
	int64_t cost = 0;
	std::string failReason;
	++g_cmdN;
	if (!hit->second.validate(game, pc.payload, base, pc.seat, cost, failReason))
	{
		rejectHostCmd(game, pc, failReason.empty() ? "rejected" : failReason);
		return;
	}

	// Passed: debit the authoritative funds, apply the mutation, then broadcast
	// shared_apply (carrying the post-mutation funds) to every peer and shared_ok
	// to the initiator. The applier gets a MUTABLE payload copy so it can resolve
	// host-only RNG into it (e.g. buy serializes generated soldiers); the resolved
	// payload is what we broadcast, so replicas reconstruct instead of re-rolling.
	SavedGame* save = game->getSavedGame();
	save->setFunds(save->getFunds() - cost);
	Json::Value payload = pc.payload;
	hit->second.apply(game, payload, base, pc.seat);
	++g_applyN;

	Json::Value apply;
	apply["state"] = "shared_apply";
	apply["cmd"] = pc.cmd;
	apply["seq"] = pc.seq;
	apply["seat"] = pc.seat;
	apply["baseId"] = pc.baseId;
	apply["payload"] = payload;
	apply["funds"] = Json::Value::Int64(save->getFunds());
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
		ok["state"] = "shared_ok";
		ok["seq"] = pc.seq;
		game->getCoopMod()->sendTCPPacketData(ok.toStyledString());
		++g_okN;
	}

	// PRD-J10: the host's own open screens are as stale as a replica's after an
	// apply (a client's buy moves the host's funds too), so both roles notify.
	fireApplyListener(pc.cmd, pc.baseId, pc.seat);
}

// ---- Replica-side apply (main thread) ----------------------------------------
void processApply(Game* game, const Json::Value& ap)
{
	SavedGame* save = game->getSavedGame();
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
	Base* base = resolveBase(game, ap.get("baseId", -1).asInt());
	auto& reg = registry();
	auto hit = reg.find(cmd);
	// NOTE: no "!base" early-return here. A creation command (base_new) carries
	// baseId=-1 (no existing base) and its applier ignores @a base; every OTHER
	// applier already null-guards @a base itself (if (!base) return;), so passing a
	// null base straight through is safe and keeps base creation working on replicas.
	if (hit == reg.end()) return;

	// Mutable copy for the applier signature; the replica only READS the resolved
	// payload (host already resolved any RNG before broadcasting).
	Json::Value payload = ap["payload"];
	int seat = ap.get("seat", 0).asInt();
	hit->second.apply(game, payload, base, seat);
	++g_applyN;

	// PRD-J10: tell the open screen its world just moved under it.
	fireApplyListener(cmd, ap.get("baseId", -1).asInt(), seat);
}

} // anonymous namespace

// ---- Public API --------------------------------------------------------------
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

void ScreenRefresh::bind(Game* game, const void* owner, Base* base, bool wantProgress)
{
	if (!game || !game->getCoopMod() || !game->getCoopMod()->isSharedCampaign()) return;
	_game = game;
	_base = base;
	_wantProgress = wantProgress;
	_bound = true;
	setApplyListener(owner, [this](const std::string& cmd, int applyBaseId)
	{
		// day_tick is pure progress bookkeeping (wound recovery, research/production
		// "days left"). List views want it; a command screen must NOT throw away the
		// player's half-entered order once per game-day because of it.
		if (!_wantProgress && cmd == "day_tick") return;
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
	registerCmd("sack",          &sackValidate,         &sackApply);
	registerCmd("base_new",      &baseNewValidate,      &baseNewApply);
	// PRD-J07 base_destroyed: host-originated (retaliation, J04); replica-only apply.
	registerCmd("base_destroyed", &simAccept, &baseDestroyedApply);
	// PRD-J08 craft orders (any player -> host; last-command-wins by arrival order).
	registerCmd("craft_launch",   &craftOrderValidate,  &craftOrderApply);
	registerCmd("craft_retarget", &craftOrderValidate,  &craftOrderApply);
	registerCmd("craft_return",   &craftExistsValidate, &craftReturnApply);
	registerCmd("craft_patrol",   &craftExistsValidate, &craftPatrolApply);

	// PRD-J09: shared-world squad assembly (mixed-owner deployment).
	registerCmd("craft_assign",   &craftAssignValidate, &craftAssignApply);
	// PRD-J09 GAP-5: shared-world craft equipment loadout (base-screen equip).
	registerCmd("craft_equip",    &craftEquipValidate,  &craftEquipApply);
	// PRD-J09 GAP-5b: the sibling base-screen store mutators (arm/rearm a craft
	// weapon; change a soldier's armor - SoldierArmorState + CraftArmorState).
	registerCmd("craft_rearm",    &craftRearmValidate,  &craftRearmApply);
	registerCmd("soldier_armor",  &soldierArmorValidate, &soldierArmorApply);
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
	// Host-authoritative alien-base discovery: a shared-world mutation, so the replica
	// must NOT roll its own (it used to, and the two could disagree).
	registerCmd("alien_base_found", &simAccept, &alienBaseFoundApply);
	// Missile-UFO base bombardment: facilities lost host-side must reach the replica
	// (shared world), and the "damaged but survived" dialog with it.
	registerCmd("base_damaged", &simAccept, &baseDamagedApply);
	// PRD-J04 host simulation-result mirrors (always-accept validator; appliers
	// run replica-side only).
	registerCmd("research_done",    &simAccept, &researchDoneApply);
	registerCmd("fac_done",         &simAccept, &facDoneApply);
	registerCmd("prod_done",        &simAccept, &prodDoneApply);
	registerCmd("transfer_arrived", &simAccept, &transferArrivedApply);
	registerCmd("day_tick",         &simAccept, &dayTickApply);
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

bool onMessage(Game* game, const std::string& state, const Json::Value& obj)
{
	if (state == "shared_cmd")
	{
		// Only the host validates/applies commands; a replica ignores stray cmds.
		if (isHost())
		{
			PendingCmd pc;
			pc.cmd = obj.get("cmd", "").asString();
			pc.seq = obj.get("seq", 0).asInt();
			pc.seat = obj.get("seat", 0).asInt();
			pc.baseId = obj.get("baseId", -1).asInt();
			pc.payload = obj["payload"];
			pc.remote = true;
			std::lock_guard<std::mutex> lk(g_mx);
			g_cmdQ.push_back(std::move(pc));
		}
		return true;
	}
	if (state == "shared_apply")
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
	if (state == "shared_ok")
	{
		++g_okN; // informational: the mutation self-applies from shared_apply
		return true;
	}
	if (state == "shared_fail")
	{
		std::string reason = obj.get("reason", "").asString();
		++g_failN;
		setLastFail(reason);
		std::lock_guard<std::mutex> lk(g_mx);
		g_failQ.push_back(reason);
		return true;
	}
	if (state == "shared_resync_request")
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

	// 1) Host: drain queued commands -> validate, debit, apply, broadcast.
	for (;;)
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

	// 2) Replica: drain queued applies -> setFunds + apply.
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

	// 3) Initiator: surface queued failures (one dialog per fail).
	for (;;)
	{
		std::string reason;
		bool have = false;
		{
			std::lock_guard<std::mutex> lk(g_mx);
			if (!g_failQ.empty()) { reason = g_failQ.front(); g_failQ.pop_front(); have = true; }
		}
		if (!have) break;
		showFail(game, reason);
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
		if (!coop || !coop->getServerOwner() || !coop->isSharedCampaign()) continue;
		++g_resyncReqN;
		Log(LOG_WARNING) << "[SHARED] resync requested by the replica; re-streaming"
			<< " the authoritative world";
		coop->sharedResyncStream();
	}
}

void submitLocalCmd(Game* game, const std::string& cmd, int baseId,
                    const Json::Value& payload)
{
	if (!game) return;
	int seq = ++g_seqCounter;
	int seat = connectionTCP::localSeat();

	if (isHost())
	{
		// Host originates: queue for local validate+apply+broadcast (unified with
		// the client-cmd path in update(); host-origin skips the shared_cmd wire).
		PendingCmd pc;
		pc.cmd = cmd;
		pc.seq = seq;
		pc.seat = seat;
		pc.baseId = baseId;
		pc.payload = payload;
		pc.remote = false;
		std::lock_guard<std::mutex> lk(g_mx);
		g_cmdQ.push_back(std::move(pc));
	}
	else
	{
		// Replica: send the command to the host; mutate nothing locally.
		Json::Value msg;
		msg["state"] = "shared_cmd";
		msg["cmd"] = cmd;
		msg["seq"] = seq;
		msg["seat"] = seat;
		msg["baseId"] = baseId;
		msg["payload"] = payload;
		if (game->getCoopMod()) game->getCoopMod()->sendTCPPacketData(msg.toStyledString());
	}
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
	return game && game->getCoopMod() && game->getCoopMod()->isSharedCampaign()
		&& connectionTCP::getHost();
}
}

void hostResearchDone(Game* game, int baseId, const std::string& research,
                      const std::string& bonus, const std::string& newResearch)
{
	if (!sharedHost(game)) return;
	Json::Value p;
	p["research"] = research;
	p["bonus"] = bonus;
	p["newResearch"] = newResearch;
	submitLocalCmd(game, "research_done", baseId, p);
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
                        int units, int progress, bool sell)
{
	if (!sharedHost(game)) return;
	Json::Value p;
	p["manufacture"] = manufacture;
	p["units"] = units;
	p["progress"] = progress;
	// GAP-6b: carry the host Production's SELL flag so the replica materializes
	// exactly what the host did (sold -> funds only, nothing to stores).
	p["sell"] = sell;
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

void submitCraftAssign(Game* game, Craft* craft, Soldier* soldier, bool onOff)
{
	if (!game || !craft || !soldier) return;
	Json::Value p;
	p["craftId"] = craft->getId();
	p["craftType"] = craft->getRules()->getType();
	p["soldierId"] = soldier->getId();
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
	submitLocalCmd(game, "alien_base_found", 0, p);
}

void hostAlert(Game* game, const std::string& cls, const std::string& msg,
               Base* base, int craftId, const std::vector<std::string>& names,
               const std::vector<int>& ids, bool flag, const Json::Value& rows)
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
	submitLocalCmd(game, "alert", base ? baseIndex(game, base) : 0, p);
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
	if (!coop || !coop->isSharedCampaign()) return true; // solo/SEPARATE: not owner-gated
	return soldier->getOwnerPlayerId() == connectionTCP::localSeat();
}

std::vector<Soldier*> visibleSoldiers(Game* game, Base* base)
{
	std::vector<Soldier*> out;
	if (!base) return out;
	connectionTCP* coop = game ? game->getCoopMod() : nullptr;
	bool shared = coop && coop->isSharedCampaign();
	int seat = shared ? connectionTCP::localSeat() : -1;
	for (auto* s : *base->getSoldiers())
	{
		if (!shared || s->getOwnerPlayerId() == seat)
			out.push_back(s);
	}
	return out;
}

void hostDayTick(Game* game)
{
	if (!sharedHost(game)) return;
	SavedGame* save = game->getSavedGame();
	if (!save) return;
	auto* bases = save->getBases();
	for (int bi = 0; bi < (int)bases->size(); ++bi)
	{
		Base* base = (*bases)[bi];
		Json::Value soldiers(Json::arrayValue);
		for (auto* soldier : *base->getSoldiers())
		{
			int id = soldier->getId();
			int rec = soldier->getWoundRecoveryInt();
			auto hit = g_soldierRecovery.find(id);
			if (hit == g_soldierRecovery.end() || hit->second != rec)
			{
				g_soldierRecovery[id] = rec;
				Json::Value js;
				js["id"] = id;
				js["recovery"] = rec;
				soldiers.append(js);
			}
		}
		// PRD-J06: carry each running production's _timeSpent and each research
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
}

// ---- PRD-J04 detect + PRD-J10 repair: world checksum -------------------------
const int RESYNC_COOLDOWN_MINUTES = 60; // one game hour between auto-resyncs
const int RESYNC_DEBOUNCE_MS = 3000;    // a mismatch must survive this to count

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
} // namespace

// ---- PRD-P2: battlescape drift tripwire (3a stamp + 3b compare) --------------
namespace {
bool g_battleDesyncSeen = false;      // harness flag: the tripwire fired here
bool g_battleMismatchLogged = false;  // one log line per mismatch EPISODE
int64_t g_lastBattleNotifyMs = -1;    // player notify throttle (RESYNC_DEBOUNCE_MS)
bool g_desyncReportWritten = false;   // ONE diagnostic bundle per battle per machine
std::string g_desyncReportPath;       // ... and where it went

// FNV-1a. std::hash is implementation-defined and the two machines are not
// necessarily the same build (Windows .exe vs the Linux AppImage), so the census
// mix has to be spelled out to be comparable ACROSS the wire.
uint64_t fnv1a(const std::string& s)
{
	uint64_t h = 1469598103934665603ULL;
	for (char c : s)
	{
		h ^= (uint64_t)(unsigned char)c;
		h *= 1099511628211ULL;
	}
	return h;
}
} // namespace

// The unit term's status field. NOT the raw UnitStatus: STANDING / WALKING /
// FLYING / TURNING / AIMING / COLLAPSING / PANICKING / BERSERK are ANIMATION
// phases, and the two machines are never on the same animation frame - the peer
// is a display that lags the executor by whatever the packet took to arrive.
// Hashing the raw enum would fire on every turn where anything was still moving.
//
// What must agree is the one classification the protocol really does replicate
// and that nothing may quietly disagree about: is this unit on its feet, dead, or
// unconscious. That is exactly BattleUnit::isOut() refined by WHICH of the two
// out-states it is (dead vs merely stunned is a real difference - a stunned unit
// can wake up and shoot), and it is the term the PRD-P9 soak asserts.
int unitLiveness(const BattleUnit* unit)
{
	switch (unit->getStatus())
	{
	case STATUS_DEAD:        return 1;
	case STATUS_UNCONSCIOUS: return 2;
	case STATUS_IGNORE_ME:   return 3;  // isOut() counts this too (isIgnored())
	default:                 return 0;  // on its feet, however it is animating
	}
}

bool battleChecksumTerms(Game* game, int64_t& itemIdCounter, int64_t& census,
						 int64_t& units)
{
	itemIdCounter = -1;
	census = -1;
	units = -1;
	if (!game || !game->getSavedGame()) return false;
	SavedBattleGame* battle = game->getSavedGame()->getSavedBattle();
	if (!battle) return false;

	itemIdCounter = battle->getCurrentItemIdValue();
	uint64_t sum = 0;
	for (BattleItem* item : *battle->getItems())
	{
		if (!item) continue;
		uint64_t h = fnv1a(item->getRules() ? item->getRules()->getType() : std::string("?"));
		h = (h ^ (uint64_t)(int64_t)item->getId()) * 1099511628211ULL;
		h = (h ^ (uint64_t)(int64_t)(item->getOwner() ? item->getOwner()->getId() : -1)) * 1099511628211ULL;
		// SUM, not a rolling hash: _items order is not replicated, so the term must
		// not depend on it. Identity (id + type + owner) is what has to agree.
		sum += h;
	}
	// Fold into the non-negative range: a negative wire value is the "the peer did
	// not stamp this" sentinel and must never be producible by a real battle.
	census = (int64_t)(sum & 0x3FFFFFFFFFFFFFFFULL);

	// The unit term. FIELDS: id, faction, liveness (see unitLiveness) and position.
	//
	// DELIBERATELY EXCLUDED, every one of them because it is known to differ
	// LEGITIMATELY at the instant this is compared:
	//   * TU / energy of a NON-player unit. An alien's remaining TU is spent by AI
	//     that runs on the executor alone and reaction fire leaves it a point or
	//     two apart here - a pre-existing classic co-op accounting seam the soak
	//     reports rather than asserts (test_parallel_soak.tu_report).
	//   * TU / energy at all. Only the walk packet and the two cost packets carry
	//     energy, and BOTH machines regenerate TU in their own prepareNewTurn -
	//     which straddles this very stamp.
	//   * health / stun / fatal wounds / morale / mana. Same reason: prepareNewTurn
	//     bleeds fatal wounds and recovers stun independently on each machine, so
	//     whether the stamp was taken before or after that pass is a coin flip.
	//   * the raw animation status and the facing (see unitLiveness).
	// What is left is the intersection with the set the PRD-P9 soak ASSERTS after
	// every side - id, position, isOut - which many clean soaks have shown to be
	// drift-free at a side boundary, plus faction (mind control replicates through
	// `psi_result` immediately in PVE, and PVP's deferred flip is not a mode this
	// term is compared in) and the dead/unconscious split isOut() collapses.
	uint64_t usum = 0;
	for (BattleUnit* unit : *battle->getUnits())
	{
		if (!unit) continue;
		const Position p = unit->getPosition();
		uint64_t h = 1469598103934665603ULL;
		h = (h ^ (uint64_t)(int64_t)unit->getId()) * 1099511628211ULL;
		h = (h ^ (uint64_t)(int64_t)(int)unit->getFaction()) * 1099511628211ULL;
		h = (h ^ (uint64_t)(int64_t)unitLiveness(unit)) * 1099511628211ULL;
		h = (h ^ (uint64_t)(int64_t)p.x) * 1099511628211ULL;
		h = (h ^ (uint64_t)(int64_t)p.y) * 1099511628211ULL;
		h = (h ^ (uint64_t)(int64_t)p.z) * 1099511628211ULL;
		// SUM again, for the same reason as the item census: _units order is not
		// something the protocol replicates.
		usum += h;
	}
	units = (int64_t)(usum & 0x3FFFFFFFFFFFFFFFULL);
	return true;
}

void attachBattleChecksum(Game* game, Json::Value& msg)
{
	// coop (#151): PvP (gamemodes 2/3) runs a ROLE-AWARE sim where the two machines
	// diverge BY DESIGN - PvP is outside all parallel + I0 sync machinery, so the
	// battle drift tripwire must not stamp the battle terms there. An unstamped peer
	// reads back as the -1 "agree" sentinel in verifyBattleChecksum, so a mixed
	// old/new-version session stays compatible. The SHARED-economy world checksum
	// (chkFunds/chkBases/... in attachWorldChecksum) is a DIFFERENT mechanism that
	// PvP campaigns still use, and is left unconditional.
	if (connectionTCP::getCoopGamemode() == 2 || connectionTCP::getCoopGamemode() == 3) return;
	int64_t itemIdCounter, census, units;
	if (!battleChecksumTerms(game, itemIdCounter, census, units)) return; // no battle
	msg["chkBattleItemId"] = Json::Value::Int64(itemIdCounter);
	msg["chkBattleCensus"] = Json::Value::Int64(census);
	msg["chkBattleUnits"] = Json::Value::Int64(units);
}

void verifyBattleChecksum(Game* game, const Json::Value& msg, const std::string& context)
{
	// coop (#151): symmetric with attachBattleChecksum - PvP (gamemodes 2/3) diverges
	// by design, so this machine must never compare the battle terms or fire the
	// desync capture in PvP. Belt-and-braces on the receive side: even a mixed-version
	// peer that still stamped chkBattle* must not trip the tripwire here. (The I0
	// per-action sync-check is already inert in PvP via parallelTurnActive() == gm 1/4.)
	if (connectionTCP::getCoopGamemode() == 2 || connectionTCP::getCoopGamemode() == 3) return;
	const int64_t peerItemId = msg.get("chkBattleItemId", -1).asInt64();
	const int64_t peerCensus = msg.get("chkBattleCensus", -1).asInt64();
	// Additive: a peer that predates the unit term stamps nothing here, which reads
	// back as the same -1 "agree" sentinel the other two use.
	const int64_t peerUnits = msg.get("chkBattleUnits", -1).asInt64();
	if (peerItemId < 0 && peerCensus < 0 && peerUnits < 0) return; // old peer / no battle

	int64_t myItemId, myCensus, myUnits;
	if (!battleChecksumTerms(game, myItemId, myCensus, myUnits)) return; // no battle here

	// coop (PRD-P10): not comparable mid-death. A death replay that is still
	// QUEUED here has not minted its corpse yet, so both terms are legitimately
	// one death behind the stamp - and `next_turn` lands in that window whenever
	// the alien side's last casualty dies a frame or two before the side closes.
	// Skipping is right rather than merely quiet: the next stamp compares the
	// same two machines once this one has caught up.
	if (corpseReplayPendingAny())
	{
		Log(LOG_INFO) << "[COOP] battle checksum on " << context
					  << " skipped - a death replay here has not converted yet";
		return;
	}

	// coop: the unit term is a QUIESCENT-state invariant - where every unit is and
	// whether it is down. `next_turn` carries no subject, so the in-order receive
	// pump lets it overtake a per-unit chain it could not consume in the same pass
	// (PRD-P11's design, and correct: the snapshot is a repair). While it has, this
	// machine is one walk or one death behind the peer THROUGH THE PROTOCOL WORKING
	// AS INTENDED - the deferred chain applies a tick later and lands on the same
	// tile. Comparing there reports a divergence that never existed. Measured in a
	// PRD-P9 soak: an alien three tiles and 12 TU apart at the stamp, identical
	// again by the time the side settled.
	//
	// The ITEM terms keep comparing unconditionally: an item id minted on one
	// machine only is not a state a late chain can heal.
	const bool unitsComparable = !rxPassDeferred();
	if ((peerItemId < 0 || peerItemId == myItemId)
		&& (peerCensus < 0 || peerCensus == myCensus)
		&& (peerUnits < 0 || !unitsComparable || peerUnits == myUnits))
	{
		if (g_battleMismatchLogged)
		{
			Log(LOG_INFO) << "[COOP] battle checksum back in agreement with the peer";
			g_battleMismatchLogged = false;
		}
		return;
	}

	// DETECTION ONLY. Whatever diverged, the battle cannot be repaired in place:
	// sharedResyncStream replaces this machine's entire state stack, which mid-battle
	// means destroying the running battle. Report and let the players finish.
	g_battleDesyncSeen = true;
	SavedBattleGame* battle = game->getSavedGame()->getSavedBattle();
	if (!g_battleMismatchLogged)
	{
		g_battleMismatchLogged = true;
		BattlescapeGame* bg = battle->getBattleGame();
		const BattleUnit* sel = battle->getSelectedUnit();
		// WHICH TERM diverged is the first question a reader has - the three watch
		// different things (item identity, item-id minting, unit position/liveness)
		// and point at completely different families of bug.
		std::string which;
		if (peerItemId >= 0 && peerItemId != myItemId) which += "itemId ";
		if (peerCensus >= 0 && peerCensus != myCensus) which += "census ";
		if (peerUnits >= 0 && unitsComparable && peerUnits != myUnits) which += "units ";
		// "Last action context" is what exists pre-PRD-P6: the packet that carried
		// the stamp, the turn, and this machine's live action/selection. P6's
		// action_seq replaces the last two once intents are numbered.
		Log(LOG_ERROR) << "[COOP] BATTLE DESYNC on " << context
			<< ": term(s) " << which
			<< "- itemId peer=" << peerItemId << " local=" << myItemId
			<< ", census peer=" << peerCensus << " local=" << myCensus
			<< ", units peer=" << peerUnits << " local=" << myUnits
			<< ", turn=" << battle->getTurn()
			<< ", side=" << (int)battle->getSide()
			<< ", items=" << (int)battle->getItems()->size()
			<< ", localAction=" << (bg ? (int)bg->getCurrentAction()->type : -1)
			<< ", selected=" << (sel ? sel->getId() : -1);

		// A sum says THAT the unit sets differ, never WHICH unit - and unlike the
		// item census there is no `battle_items` equivalent a player can be asked
		// to run. So the unit term dumps its own inputs, once, bounded by the unit
		// count (a battle has tens): diffing the two machines' log lines then names
		// the unit in one step. Same fields the term hashes, in the same order.
		if (peerUnits >= 0 && unitsComparable && peerUnits != myUnits)
		{
			std::ostringstream dump;
			for (BattleUnit* u : *battle->getUnits())
			{
				if (!u) continue;
				const Position p = u->getPosition();
				dump << " " << u->getId() << ":f" << (int)u->getFaction()
					 << "/l" << unitLiveness(u) << "/s" << (int)u->getStatus()
					 << "@" << p.x << "," << p.y << "," << p.z;
			}
			Log(LOG_ERROR) << "[COOP] BATTLE DESYNC units here (id:faction/liveness/"
						   << "rawstatus@x,y,z):" << dump.str();
		}
	}

	// Auto-report. AFTER the log line above on purpose - the bundle copies the log
	// file, and that line is the entry point a developer reads first. Latched
	// internally to one bundle per battle, so the repeat compares that follow for
	// the rest of the battle cost nothing.
	{
		DesyncTerms report;
		report.peerItemId = peerItemId;
		report.localItemId = myItemId;
		report.peerCensus = peerCensus;
		report.localCensus = myCensus;
		report.peerUnits = peerUnits;
		report.localUnits = myUnits;
		report.context = context;
		captureDesyncReport(game, report);
	}

	// One player-facing notify per debounce window - the same constant the world
	// checksum debounces on - so a term that stays wrong for the rest of the battle
	// does not spam the map.
	const int64_t nowMs = steadyMs();
	if (g_lastBattleNotifyMs >= 0 && nowMs - g_lastBattleNotifyMs < RESYNC_DEBOUNCE_MS) return;
	g_lastBattleNotifyMs = nowMs;
	if (BattlescapeState* bs = battle->getBattleState())
	{
		// The in-battle warning banner, NOT a modal: pushing a CoopState over a live
		// battle is the dialog/dismiss trap, and the tripwire must never disturb the
		// state stack it is diagnosing. warningLongRaw() self-suppresses while the
		// peer is acting (isYourTurn == 1); the log line above is unconditional.
		bs->warningLongRaw("CO-OP DESYNC DETECTED - SEE openxcom.log");
	}
}

bool battleDesyncSeen()
{
	return g_battleDesyncSeen;
}

void resetBattleDesyncSeen()
{
	g_battleDesyncSeen = false;
	g_battleMismatchLogged = false;
	g_lastBattleNotifyMs = -1;
	// The bundle latch lives here: one report per battle per machine, cleared by
	// the same reset (resetResyncStats / the harness' shared_reset_resync_stats)
	// that clears the tripwire itself.
	g_desyncReportWritten = false;
	g_desyncReportPath.clear();
}

// ---- Desync auto-report bundle -----------------------------------------------
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
std::string desyncTimeString(const char* format)
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

/// One zip from in-memory members. Heap writer only - see the include note at the
/// top of this file for why the file-based writer APIs are off limits.
bool writeZipArchive(const std::string& path,
					 const std::vector<std::pair<std::string, std::string> >& members)
{
	if (members.empty()) return false;
	mz_zip_archive zip;
	std::memset(&zip, 0, sizeof(zip));
	if (!mz_zip_writer_init_heap(&zip, 0, 256 * 1024)) return false;

	bool ok = true;
	for (size_t i = 0; ok && i < members.size(); ++i)
	{
		ok = (mz_zip_writer_add_mem(&zip, members[i].first.c_str(),
									members[i].second.data(), members[i].second.size(),
									MZ_DEFAULT_COMPRESSION) != MZ_FALSE);
	}

	void* buf = 0;
	size_t size = 0;
	if (ok) ok = (mz_zip_writer_finalize_heap_archive(&zip, &buf, &size) != MZ_FALSE);
	if (ok && buf != 0 && size != 0)
	{
		// The vector<unsigned char> overload, NOT the std::string one: that opens
		// the file in TEXT mode, which on Windows rewrites every 0x0A in the
		// deflate stream and produces a zip nothing can open.
		const unsigned char* first = (const unsigned char*)buf;
		std::vector<unsigned char> bytes(first, first + size);
		ok = CrossPlatform::writeFile(path, bytes);
	}
	// finalize_heap_archive HANDS OVER the block (it nulls m_pMem), so it survives
	// writer_end and this function owns the free.
	if (buf) mz_free(buf);
	mz_zip_writer_end(&zip);
	return ok;
}

/// The sim-state dump. Goes through the ordinary save path - SavedGame::save, the
/// same one co-op's autosave, quicksave and deferred host save use - which
/// resolves its filename inside the master user folder. So: write a temp, read
/// the bytes back, delete the temp. `.tmp` rather than `.sav`/`.asav` on purpose,
/// because the LOAD list scans only those two: a delete that somehow fails still
/// cannot leave a phantom entry in the player's save list.
bool captureForcedSave(Game* game, std::string& out)
{
	out.clear();
	if (!game || !game->getSavedGame() || !game->getMod()) return false;
	const std::string tmpName = "_desync_capture_.tmp";
	const std::string tmpPath = Options::getMasterUserFolder() + tmpName;
	bool ok = false;
	try
	{
		game->getSavedGame()->save(tmpName, game->getMod());
		ok = readTailBinary(tmpPath, 0, out);
	}
	catch (const std::exception& e)
	{
		Log(LOG_ERROR) << "[COOP] desync report: forced save failed: " << e.what();
	}
	catch (...)
	{
		Log(LOG_ERROR) << "[COOP] desync report: forced save failed";
	}
	if (CrossPlatform::fileExists(tmpPath)) CrossPlatform::deleteFile(tmpPath);
	if (!ok) out.clear();
	return ok;
}

/// The context a log line cannot carry: both machines' checksum terms, the battle
/// and parallel-turn counters, who this seat is, what build and which mods.
std::string buildDesyncInfo(Game* game, const DesyncTerms& terms,
							const Json::Value& attribution)
{
	Json::Value root;
	root["schema"] = 1;
	root["generated"] = desyncTimeString("%Y-%m-%d %H:%M:%S");
	root["context"] = terms.context.empty() ? std::string("unknown") : terms.context;
	root["detected"] = terms.viaPeerReport ? "peer_report" : "local_compare";

	Json::Value chk;
	chk["peer_itemId"] = Json::Value::Int64(terms.peerItemId);
	chk["local_itemId"] = Json::Value::Int64(terms.localItemId);
	chk["peer_census"] = Json::Value::Int64(terms.peerCensus);
	chk["local_census"] = Json::Value::Int64(terms.localCensus);
	chk["peer_units"] = Json::Value::Int64(terms.peerUnits);
	chk["local_units"] = Json::Value::Int64(terms.localUnits);
	root["checksum"] = chk;

	SavedGame* save = game ? game->getSavedGame() : 0;
	SavedBattleGame* battle = save ? save->getSavedBattle() : 0;
	Json::Value b;
	b["live"] = (battle != 0);
	if (battle)
	{
		b["turn"] = battle->getTurn();
		b["side"] = (int)battle->getSide();
		b["items"] = (int)battle->getItems()->size();
		b["units"] = (int)battle->getUnits()->size();
		const BattleUnit* sel = battle->getSelectedUnit();
		b["selected_unit"] = sel ? sel->getId() : -1;
		BattlescapeGame* bg = battle->getBattleGame();
		b["local_action"] = bg ? (int)bg->getCurrentAction()->type : -1;
		b["busy"] = bg ? bg->isBusy() : false;
	}
	b["coop_turn"] = BattlescapeGame::isYourTurn;
	root["battle"] = b;

	Json::Value p;
	p["parallel_active"] = connectionTCP::parallelTurnActive();
	p["parallel_enabled"] = connectionTCP::_enable_parallel_turns;
	p["action_seq"] = (Json::UInt)connectionTCP::_actionSeq;
	p["side_seq"] = (Json::UInt)connectionTCP::_sideSeq;
	p["peer_display_acked_seq"] = (Json::UInt)connectionTCP::peerDisplayAckedSeq;
	p["client_pending_req_id"] = (Json::UInt)connectionTCP::_clientPendingReqId;
	p["active_sync"] = connectionTCP::_isActivePlayerSync;
	p["battle_init"] = connectionTCP::_battleInit;
	if (connectionTCP* coop = game ? game->getCoopMod() : 0)
	{
		p["task_depth"] = coop->coopTaskDepth();
		p["task_completed"] = coop->coopTaskCompleted();
		p["path_lock"] = coop->_pathLock;
		p["coop_end"] = coop->_coopEnd;
	}
	root["parallel_state"] = p;

	Json::Value s;
	s["gamemode"] = connectionTCP::getCoopGamemode();
	s["seat"] = connectionTCP::localSeat();
	s["host"] = connectionTCP::getHost();
	s["connected"] = connectionTCP::getCoopStatic();
	s["shared_campaign"] = connectionTCP::isSharedCampaignStatic();
	s["save_id"] = Json::Value::Int64((int64_t)connectionTCP::saveID);
	if (connectionTCP* coop = game ? game->getCoopMod() : 0)
	{
		// Machine-relative, not role-relative: getHostName() is THIS player,
		// getCurrentClientName() is the peer (see the co-op name-getter note).
		s["local_player"] = coop->getHostName();
		s["peer_player"] = coop->getCurrentClientName();
	}
	root["session"] = s;

	Json::Value v;
	v["version"] = std::string(OPENXCOM_VERSION_SHORT) + OPENXCOM_VERSION_GIT;
	v["engine"] = OPENXCOM_VERSION_ENGINE;
	v["oxce"] = OPENXCOM_VERSION_OXCE;
	v["save_schema"] = (int)SAVE_SCHEMA_CURRENT;
	v["platform"] = desyncPlatform();
	root["build"] = v;

	// No crash-log modlist helper exists in this tree; this is the same
	// "<id> ver: <version>" line SavedGame::save writes into every save header.
	Json::Value mods(Json::arrayValue);
	for (const ModInfo* mi : Options::getActiveMods())
	{
		if (mi) mods.append(mi->getId() + " ver: " + mi->getVersion());
	}
	root["mods"] = mods;

	// PRD-I4: the sync-check attribution - the offending seq/kind/bucket, the
	// per-bucket table and a ring snapshot - so a bundle names WHICH action
	// diverged, not just that the terms disagree.
	root["attribution"] = attribution;
	desyncEmbedSyncState(root);

	return root.toStyledString();
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

/// The prefilled GitHub issue body: the attribution table plus the "attach the
/// zip" instruction. Plain text; the caller URL-encodes it. NO auto-upload.
std::string desyncIssueBody(const DesyncTerms& terms, const Json::Value& attribution,
							const std::string& path)
{
	std::ostringstream b;
	b << "A co-op battle desync was auto-detected.\n\n";
	b << "Attribution: " << attribution.get("headline", "unknown").asString() << "\n";
	b << "  source: " << attribution.get("source", "?").asString()
	  << "  seq: " << attribution.get("seq", 0).asUInt()
	  << "  kind: " << attribution.get("kind", "").asString()
	  << "  bucket: " << attribution.get("bucket", "").asString() << "\n\n";
	b << "Checksum terms (peer vs local):\n";
	b << "  itemIdCounter: " << terms.peerItemId << " vs " << terms.localItemId << "\n";
	b << "  battleCensus:  " << terms.peerCensus << " vs " << terms.localCensus << "\n";
	b << "  battleUnits:   " << terms.peerUnits << " vs " << terms.localUnits << "\n\n";
	b << "Please ATTACH the diagnostic zip (do not paste it) to this issue:\n";
	b << "  " << path << "\n\n";
	b << "(auto-generated by the co-op desync reporter; log + save + context are in the zip)\n";
	return b.str();
}

/// PRD-I5: the crash bundle's system-info json. Mirrors buildDesyncInfo's build +
/// mods block (the I4 json builder the PRD asks us to reuse), plus the marker echo
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
	root["generated"] = desyncTimeString("%Y-%m-%d %H:%M:%S");

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

/// PRD-I5: parse + validate the crash marker. Read through readTailBinary (the
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

// ---- PRD-I5 dual-source discovery: crashlogs scan + seen-ledger -------------
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
	const std::string tsF = tsFile.empty() ? desyncTimeString("%Y%m%d-%H%M%S") : tsFile;
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

bool desyncReportWritten()
{
	return g_desyncReportWritten;
}

std::string desyncReportPath()
{
	return g_desyncReportPath;
}

void captureDesyncReport(Game* game, const DesyncTerms& terms)
{
	// LATCH FIRST, before anything that can fail. A full disk, a read-only user
	// folder, a save that throws - none of them may put this back in the firing
	// line, because the tripwire re-compares on every next_turn for the rest of
	// the battle and a retry loop writing multi-megabyte bundles is far worse
	// than the desync it is reporting.
	if (g_desyncReportWritten) return;
	g_desyncReportWritten = true;

	// PRD-I4: attribution (offending bucket/seq/kind, or the diverged terms) drives
	// the desync_report packet, the desync-info.json, the dialog headline and the
	// prefilled GitHub issue. Computed once, before any (fallible) capture work.
	const Json::Value attribution = desyncComputeAttribution(game, terms);
	const std::string headline = attribution.get("headline", "").asString();

	try
	{
		// Tell the peer BEFORE doing our own (slow) work: its half of the pair is
		// only worth having if it is captured at nearly the same instant. A
		// machine that was itself told never re-sends - that is the ping-pong.
		if (!terms.viaPeerReport && game && game->getCoopMod() && connectionTCP::getCoopStatic())
		{
			SavedGame* sg = game->getSavedGame();
			SavedBattleGame* battle = sg ? sg->getSavedBattle() : 0;
			Json::Value root;
			root["state"] = "desync_report";
			root["turn"] = battle ? battle->getTurn() : 0;
			root["side"] = battle ? (int)battle->getSide() : -1;
			// Named from the RECEIVER's point of view: what it will record as its
			// peer's terms is what this machine holds locally.
			root["peer_itemId"] = Json::Value::Int64(terms.localItemId);
			root["peer_census"] = Json::Value::Int64(terms.localCensus);
			root["peer_units"] = Json::Value::Int64(terms.localUnits);
			root["context"] = terms.context;
			root["attribution"] = attribution;
			game->getCoopMod()->sendTCPPacketData(root.toStyledString());
		}

		const std::string dir = Options::getUserFolder() + "desync-reports/";
		if (!CrossPlatform::folderExists(dir)) CrossPlatform::createFolder(dir);
		if (!CrossPlatform::folderExists(dir))
		{
			Log(LOG_ERROR) << "[COOP] desync report: cannot create " << dir;
			return;
		}
		const std::string path = dir + "desync-" + desyncTimeString("%Y%m%d-%H%M%S") + ".zip";

		std::vector<std::pair<std::string, std::string> > members;
		// The json first: it is the one member that cannot fail to be produced, so
		// a bundle always says SOMETHING even if log and save are both unreadable.
		members.push_back(std::make_pair(std::string("desync-info.json"),
										 buildDesyncInfo(game, terms, attribution)));
		std::string blob;
		// The log already holds the BATTLE DESYNC line - verifyBattleChecksum logs
		// it before calling here, and Log() appends to the file per message, so the
		// copy taken now includes it.
		if (readTailBinary(CrossPlatform::getLogFileName(), DESYNC_LOG_TAIL_BYTES, blob))
		{
			members.push_back(std::make_pair(std::string("openxcom.log"), blob));
		}
		else
		{
			Log(LOG_WARNING) << "[COOP] desync report: could not read "
							 << CrossPlatform::getLogFileName();
		}
		if (captureForcedSave(game, blob))
		{
			members.push_back(std::make_pair(std::string("desync-battle.sav"), blob));
		}

		if (!writeZipArchive(path, members))
		{
			Log(LOG_ERROR) << "[COOP] desync report: failed to write " << path;
			return;
		}
		g_desyncReportPath = path;
		Log(LOG_ERROR) << "[COOP] desync diagnostic report written to " << path
					   << " (" << (int)members.size() << " members)";

		if (game && game->getLanguage())
		{
			// Post-capture UX only: the bundle is already on disk, so a modal the
			// player leaves sitting cannot spoil the diagnostic it announces.
			const std::string issueBase =
				"https://github.com/OpenXcom-Coop/OpenXcom-Coop-Mod/issues/new";
			const std::string title = "[coop desync] " +
				(headline.empty() ? std::string("battle desync") : headline);
			const std::string reportUrl = issueBase + "?title=" + desyncUrlEncode(title) +
				"&body=" + desyncUrlEncode(desyncIssueBody(terms, attribution, path));
			game->pushState(new CoopDesyncNoticeState(
				game->getLanguage()->getString("STR_COOP_DESYNC_REPORT_SAVED")
					.arg(wrapPathForDialog(path)),
				headline, path, reportUrl));
		}
	}
	catch (const std::exception& e)
	{
		Log(LOG_ERROR) << "[COOP] desync report failed: " << e.what();
	}
	catch (...)
	{
		Log(LOG_ERROR) << "[COOP] desync report failed";
	}
}

// ---- PRD-I5: next-launch crash reporter (Pattern A) -------------------------
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
// suppress one prompt - acceptable, documented in prd-i5.
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


// ---- PRD-I0: per-action sequenced sync-check --------------------------------
namespace {

// The PROMOTION TABLE, in BattleHashSet field order. Compile-time constant per
// build, exactly as PRD-I0 §3 asks for - a runtime option would let a report get
// written against a policy nobody can reconstruct afterwards.
//
// EVERY BUCKET IS REPORT-ONLY AT BIRTH. That is the instrumentation programme's
// own rule (instrumentation/README.md: "Every bucket onboards REPORT-ONLY,
// promotes to ALARM after burn-in"), and it is the only honest starting point:
// I0 ships the DETECTOR, and until each bucket has been through the PRD-I3
// burn-in nobody knows whether a red is a real divergence or an artefact of
// where the two machines take the sample. Promoting a bucket early would make
// `battleDesyncSeen` - which the soak and half a dozen other tests assert on -
// fire on known-open seams (terrain destruction, fire/smoke decay, per-unit
// stats), i.e. it would turn a working release gate into noise.
//
// PRD-I3 flips these one at a time, each with its burn-in evidence.
const bool BATTLE_HASH_ALARM[BATTLE_HASH_BUCKETS] = {
	true,   // terrain      (PRD-I3 PROMOTED 2026-08-14 Session E @e316d716a: side-gated to
	        //               player-side+sidestart like unitsCore; L3 0/36 incl. incendiary/spawn-blast/casualty)
	true,   // fire         (PRD-I3 PROMOTED 2026-08-14 @4a15f7bd4: L3 clean incl. incendiary x2)
	true,   // smoke        (PRD-I3 PROMOTED 2026-08-14 Session E @e316d716a: L3 0/36; twin of fire,
	        //               endturn hazard-skip + SEAM-3 expl stamp already closed the mid-side class)
	true,   // items        (PRD-I3 PROMOTED 2026-08-15 Session F @43ec70384: SIDE-GATE (player+sidestart)
	        //               + corpse-pending window-1/window-2 skips; #74 boundary path proven covered; L3 0)
	true,   // unitsCore    (PRD-I3 PROMOTED 2026-08-14 Session C: side-gated to player-side+sidestart; L3 clean)
	true,   // unitsStats   (PRD-I3 PROMOTED 2026-08-14: superseded=0 old-peer fallback, L3 clean)
	true,   // itemIdCtr    (PRD-I3 PROMOTED 2026-08-15 Session F @43ec70384: same side-gate + corpse-pending
	        //               skips as items; the id counter re-slaves per the P4 manifest; L3 0 everywhere)
	true,   // unitsCombat  (PRD-I3 PROMOTED 2026-08-14: CHAIN-authored kneel/mc/w0..w5; fire moved out)
	true,   // unitsRegen   (PRD-I3 PROMOTED 2026-08-14: DEFERRED set, sidestart-only, L3 clean)
};

const char* const BATTLE_HASH_NAMES[BATTLE_HASH_BUCKETS] = {
	"terrain", "fire", "smoke", "items", "unitsCore", "unitsStats", "itemIdCtr",
	"unitsCombat", "unitsRegen",
};

const std::uint64_t FNV_OFFSET = 1469598103934665603ULL;
const std::uint64_t FNV_PRIME = 1099511628211ULL;

inline std::uint64_t mix(std::uint64_t h, std::int64_t v)
{
	return (h ^ (std::uint64_t)v) * FNV_PRIME;
}

std::uint32_t g_lastSweepUs = 0;
std::uint32_t g_lastSaveBlobUs = 0;   // PRD-I2: cost of the last saveBlob serialize

/// One remembered "state after N" on the executor.
struct SyncRingEntry
{
	bool boundary;            ///< boundary pseudo-seq namespace?
	std::uint32_t seq;        ///< action_seq (per side) or boundary seq (per battle)
	std::uint32_t sideSeq;    ///< the side the action seq belongs to (0 for boundary)
	std::string kind;         ///< "walk" / "shoot" / "ai" / "endturn" / "sidestart" / ...
	bool compared;            ///< has a peer report been matched against it?
	BattleHashSet h;
	// PRD-I2: boundary-only save-derived hash. Left 0 (and never shipped) for
	// per-action entries; recorded only for boundary entries (see syncCheckRecord).
	std::uint64_t saveBlob = 0;
	// PRD-I3 SEAM-7 (opt-in): this machine's full per-unit unitsStats field vector at
	// hash time, so a unitsStats mismatch on this entry can be diffed field-by-field
	// against the peer's `uv`. Null (and cheap) unless the capture toggle is armed.
	Json::Value statVec;
};

// Size 64 per PRD-I0 §3. The display-backlog cap is 2, so the executor can never
// be more than a couple of chains ahead of the peer's reports - 64 is two orders
// of magnitude of headroom, and an overflow of an UNCOMPARED entry is therefore
// a tripwire in its own right (it means reports stopped coming back), which is
// why it logs.
const size_t SYNC_RING_MAX = 64;
std::deque<SyncRingEntry> g_syncRing;

struct SyncMismatch
{
	std::uint32_t seq;
	bool boundary;
	std::string kind;
	std::string bucket;
};
// Bounded: a battle that has gone wrong can produce one of these per action, and
// the introspection block is read by a test on every poll.
const size_t SYNC_MISMATCH_MAX = 32;
std::deque<SyncMismatch> g_syncMismatches;

// PRD-I3 SEAM-7: the exact per-unit field(s) behind a unitsStats bucket mismatch,
// recorded when the opt-in field capture rode both the ring entry and the peer report.
struct SyncFieldDiff
{
	std::uint32_t seq;
	bool boundary;
	std::string kind;
	int unitId;
	std::string field;
	std::int64_t host;
	std::int64_t peer;
};
const size_t SYNC_FIELDDIFF_MAX = 64;
std::deque<SyncFieldDiff> g_syncFieldDiffs;

std::uint64_t g_syncBucketMismatches[BATTLE_HASH_BUCKETS] = { 0 };
// PRD-I3 SEAM-2 HALF 1: per-bucket COMPARES - times a bucket was actually sampled
// cross-machine (never incremented for a bucket the compare skipped). "Was it
// compared" is a different statement from "did it mismatch", and the acceptance
// test needs the former to prove the endturn hazard exclusion below really fired.
std::uint64_t g_syncBucketCompares[BATTLE_HASH_BUCKETS] = { 0 };
// PRD-I3 SEAM-2 HALF 1: the ENDTURN boundary carries no well-defined hazard sample
// (all decay runs once per cycle at neutral->player, AFTER both endturn boundaries
// are armed, and the host flushes the endturn boundary racing its own decay), so
// its smoke/fire buckets are EXCLUDED from the comparison; the SIDESTART boundary
// (hash-after-apply of next_turn) keeps them. These count the two so a test can
// assert the split: endturn skipped, sidestart still compared.
std::uint64_t g_syncEndturnHazardSkips = 0;
std::uint64_t g_syncSidestartHazardCompares = 0;
// PRD-I3 SEAM-7: unitsRegen (tu/energy/mana) is turn-machine-authored, so its ai-seq
// and endturn-boundary samples straddle the transition (host committed toward the next
// side's regen while the client defers to next_turn). It is EXCLUDED there and compared
// only where its author makes it well-defined (player action seqs + sidestart). These
// count the two straddle exclusions so a test can assert exactly where they fired.
std::uint64_t g_syncRegenAiSkips = 0;
std::uint64_t g_syncRegenEndturnSkips = 0;
// PRD-I3 unitsCore side-gate (2026-08-14, Session C): alien-side + endturn skips.
std::uint64_t g_syncCoreAlienSkips = 0;
std::uint64_t g_syncCoreEndturnSkips = 0;
// PRD-I3 terrain side-gate (2026-08-14, Session E): the SEAM-3 residual is a
// destroy_tile mapDataID that lands one step behind the host during the alien-side
// AI/explosion replay (ai/expl per-action seqs) and at the alien-side ENDTURN
// boundary, healing by sidestart. Mirrors unitsCore: skip alien per-action + endturn,
// keep player-side per-action (strict) + sidestart. These count the two skips.
std::uint64_t g_syncTerrainAlienSkips = 0;
std::uint64_t g_syncTerrainEndturnSkips = 0;
// PRD-I3 Session F items/itemIdCtr side-gate (2026-08-15, manager sign-off after the
// boundary-death trace): SAME discipline as terrain/unitsCore. The boundary-death corpse
// mint is COVERED by the after_unit_death P4 manifest and is CLEAN in isolation (proven
// lockstep across player/alien, single/multi, bleed/fire, and a lagging slow client - the
// counter and corpse ids match on both machines). The residual items/itemIdCtr drift is an
// ALIEN-side display window: the D-lite client's gated alien replay mints/re-stamps a corpse
// one step behind the host's authoritative death resolution (ai/expl per-action seqs) and at
// the alien-side ENDTURN boundary, healing by sidestart (traced Session F seed 501: fires at
// alien ai seqs only, transient, count 2, healed before the turn's sidestart). Session E's
// "boundary sidestart" attribution was a saveBlob firing (seq 10), a conflation. Skip the
// alien per-action seqs + endturn; KEEP player-side per-action (strict) + sidestart, where a
// PERSISTENT item drift still surfaces AND the items player-seq negative control
// (test_sync_check scenario 4) still sees its mint. A skipped bucket is NOT counted as compared.
std::uint64_t g_syncItemsAlienSkips = 0;
std::uint64_t g_syncItemsEndturnSkips = 0;
// PRD-I3 Session F corpse-replay-pending skip (2026-08-15, manager belt-and-suspenders
// trigger): a report whose hash was sampled while the REPORTING machine's death replay
// has not minted its corpse yet is legitimately one death behind the executor's ring
// entry - the corpse exists on the host but not here - so its item terms (items/itemIdCtr)
// and the saveBlob superset would false-fire even at a SIDESTART (Session F seed 8003 seq
// 16: items+itemIdCtr fired at sidestart while the P2 tripwire correctly stayed quiet,
// because verifyBattleChecksum ALREADY skips on corpseReplayPendingAny - the per-action
// sync-check did not). Mirror that skip here. Transient by construction (the next report,
// after the replay drains, compares the same two machines caught up); a PERSISTENT item
// drift has no pending replay and still compares.
std::uint64_t g_syncItemsCorpsePendingSkips = 0;
std::uint64_t g_syncSaveBlobCorpsePendingSkips = 0;
// The two namespaces are tracked apart: `action_seq` restarts at 0 every side, so
// a shared watermark would be dragged forwards by the battle-monotonic boundary
// counter and "the deferred loop closed" would read true for ever after.
std::uint32_t g_syncLastSeq = 0;          ///< newest ACTION seq recorded
std::uint32_t g_syncLastComparedSeq = 0;  ///< newest ACTION seq a peer report closed
std::uint32_t g_syncLastBoundarySeq = 0;
std::uint32_t g_syncLastComparedBoundarySeq = 0;
std::uint64_t g_syncCompares = 0;         ///< reports matched to a ring entry
std::uint64_t g_syncStaleReports = 0;     ///< reports with no ring entry left
std::uint64_t g_syncDropped = 0;          ///< uncompared entries evicted by overflow
// Compared entries by kind. The only way a test can prove COVERAGE rather than
// mere silence: "the alien side ran and 7 of its chains were compared" is a
// different statement from "nothing complained", and PRD-I0's first scenario
// needs the former (a seq extension that silently stamped nothing would pass a
// zero-mismatch assertion perfectly).
std::map<std::string, std::uint64_t> g_syncKindCompares;

// PRD-I2: the save-derived boundary bucket ("saveBlob"). Kept OUT of the seven-
// bucket BattleHashSet on purpose: computed ONLY at boundaries (a 5-20 ms
// serialization, never per action), so it must not appear in the raw per-action
// `battleHashes` sweep the harness polls. Its own report-only flag + counter.
const bool SAVEBLOB_ALARM = true;    // PRD-I3 PROMOTED 2026-08-15 Session F @43ec70384:
                                     // the whole-save superset. SEAM-11 shipped ammoqty
                                     // (next_turn absolute + -1/255) + closed the ufo-door
                                     // boundary; exp*/tempUnitStatistics/motionPoints
                                     // excluded, floating shipped. L3 0 everywhere incl.
                                     // campaign. ALL TEN BUCKETS NOW ALARM.
std::uint64_t g_syncSaveBlobMismatches = 0;
// PRD-I3 saveBlob endturn straddle: the saveBlob bucket is computed ONLY at
// boundaries, and (like the smoke/fire hazard buckets in SEAM-2 HALF 1) the
// ENDTURN boundary sample is ill-defined - the whole-save hash straddles the
// deferred turn-machine state the D-lite client only resolves at next_turn. So
// the host compare EXCLUDES saveBlob at an endturn boundary and keeps it at
// SIDESTART (hash-after-apply of next_turn = well-defined). Compare-site only;
// the client still ships saveBlob in every boundary `h`, so the wire is unchanged
// and old/new peers stay symmetric. These count the two so a test can assert it.
std::uint64_t g_syncSaveBlobEndturnSkips = 0;
std::uint64_t g_syncSaveBlobSidestartCompares = 0;

// The nodes stripped BEFORE hashing (exclusion by NODE PATH on the parsed tree,
// robust to emit formatting). Two scopes, both SHORT and each entry justified.
//
// TOP-LEVEL of the battle document only - machine-local display/selection state:
bool saveBlobExcludedTopKey(std::string_view k)
{
	// selectedUnit / undoUnit: the LOCAL player's selected unit and undo pointer.
	//   Each machine drives its own units (thin-client display), so both diverge by
	//   design - the same reason the fast sweep never hashes selection.
	// animFrame: the global battlescape animation phase; the two machines are never
	//   on the same display frame (identical rationale to the terrain bucket's
	//   animation-frame skip).
	return k == "selectedUnit" || k == "undoUnit" || k == "animFrame";
	// Naturally ABSENT, so deliberately not listed: the RNG seed/state, the camera
	// and the coop_* session keys are not emitted by SavedBattleGame::save at all -
	// RNG and coop_* live in SavedGame::save (the geoscape document we do NOT
	// serialize) and the camera is BattlescapeState runtime state. Serializing the
	// battle document ONLY excludes all three for free.
}

// ANY DEPTH - host-authoritative bookkeeping the thin client never derives, plus two
// vanilla-clean mod-reader keys (exclude-for-vanilla with a caveat). The host save is
// the single authority (a resume restreams over the client's copy). Every entry was
// reader-audited (client-side mid-battle readers) for PRD-I3 SEAM-TAIL CLOSE
// 2026-08-12: a key with a gameplay-relevant CLIENT reader is SHIPPED on a death
// packet, not excluded here. Categories:
// (a) AI bookkeeping - PRD-I3 RATIFIED (closes the I2-era "must ratify" note): read
//     ONLY by the host's handleAI / pathfinding; the client runs no AI
//     (_isActivePlayerSync-gated), so no client counterpart can agree.
// (b) FOW / spotting (Option B rider) - presentation, per-machine calculateFOV.
// (c) casualty kill-bookkeeping (PRD-I3 SEAM-8 consequence): the client no longer
//     runs checkForCasualties (gate 9dadcb160), so the murderer's kill diary and the
//     victim's death record never populate there; read ONLY by checkForCasualties and
//     the host-authoritative debriefing (kills.clear()+refill per PROTOCOL), and
//     next_turn does not re-ship them, so they persist past the boundary. Zero-disk
//     client + host-replaced debrief = authority-local, safe to exclude.
bool saveBlobExcludedAnyKey(std::string_view k)
{
	// --- (a) AI bookkeeping (RATIFIED) ---
	// AI: a BattleUnit's whole AIModule sub-map (fromNode/toNode/AIMode/wasHitBy) -
	//   host-only; the client's alien units keep the defaults (toNode -1, AIMode 0).
	// aiMedikitUsed: an AI behaviour flag set only when the host's AI heals a unit.
	// allocated: a pathfinding Node claimed by the host's AI for a patrol/spawn; the
	//   client never allocates nodes.
	// --- (b) per-unit FOV / spotting (PRD-I3 FOW Option B rider) ---
	// The visibility/spotting fields BattleUnit::save writes. Under the Option B
	// contract FOW is PRESENTATION - derived locally from replicated positions,
	// never promised identical between machines - so these are a permanent
	// carve-out, exactly like the per-tile discovered bits masked out of binTiles.
	// visible: whether THIS machine currently sees the unit (per-machine FOV).
	// turnsSinceSpotted* / turnsLeftSpottedForSnipers* (the HOSTILE key plus the
	//   ByXcom / ByCivilian faction variants): per-faction spotting timers driven
	//   by each machine's own calculateFOV - FOW-class bookkeeping, not shared state.
	// --- (c) casualty kill-bookkeeping (PRD-I3 SEAM-TAIL, reader-audited) ---
	// fatalShotSide / fatalShotBodyPart / murdererWeapon / murdererWeaponAmmo /
	//   murdererId: the victim's death record (murdererId = attributed killer, set
	//   host-only in hitUnit/checkForCasualties, both coop-client early-returns; a
	//   wounded survivor's is never shipped). kills: the murderer's kill counter AND,
	//   at any depth,
	//   its tempUnitStatistics.kills diary sub-tree (excluding the map key drops the
	//   whole list). All read ONLY in checkForCasualties (host) + DebriefingState
	//   (host debrief) - no mid-battle client gameplay reader.
	// notificationShown: gates the death-notice popup + death-anim skip/speed; its
	//   writes are host/classic-gated (UnitDieBState), so on the parallel client it
	//   stays 0 - a presentation field, not gameplay state.
	// droppedOnAlienTurn (a BattleItem flag): read ONLY by surveyItems (host AI weapon
	//   pickup); the client runs no AI, so no client gameplay reader.
	// turnsSinceStunned: MOVED here from KEEP (was called "a real stun-recovery stat").
	//   The audit corrects that: recovery is stunlevel-driven; turnsSinceStunned's ONLY
	//   gameplay reader is handleAI's just-woke check (BattlescapeGame.cpp:1213,
	//   host-only). startFalling resets it to 0 on a collapse (host), which the gated
	//   client CFC never mirrors, so it diverges on a casualty. Exclude-for-vanilla; MOD
	//   CAVEAT: a ruleset script can read it (getTurnsSinceStunned binding) - the shared
	//   script-reader mod caveat (see the ledger with GAP-10 / wantsToSurrender).
	// --- (d) two decided vanilla-clean keys ---
	// exp* (expBravery/expReactions/expFiring/expThrowing/expPsiSkill/expPsiStrength/
	//   expMana/expMelee): the per-unit combat-EXPERIENCE counters (_exp.*). Accrued on
	//   the executor as a unit acts (a shot bumps expFiring, etc.), consumed ONLY at
	//   BattleUnit::postMissionProcedures (host debrief -> improveStat rolls). The parallel
	//   thin client REPLAYS the action for display without accruing the experience, so
	//   e.g. expFiring host=1 / client=0 on any firer - the DOMINANT clean-run saveBlob
	//   residual (Session F seed 8013 named it). No mid-battle client gameplay reader; the
	//   debrief stat gains are host-authoritative under the whole-world restream, exactly
	//   like the excluded kills/tempUnitStatistics diary -> exclude the whole family
	//   (expBravery was already carved out; Session F extends it to all eight).
	// wantsToSurrender: vanilla NEVER reads it; a MOD reader exists
	//   (endTurn->tallyUnits->isSurrendering, gated getSurrenderMode()>=2). Exclude-for-
	//   vanilla; MOD CAVEAT recorded in the ledger next to GAP-10 / turnsSinceStunned.
	// --- (e) Session F saveBlob dispositions (2026-08-15, manager sign-off) ---
	// tempUnitStatistics: the per-unit combat diary sub-tree (shotAtCounter / hitCounter /
	//   shotsFiredCounter / shotsLandedCounter / appliedStimulant + the already-excluded
	//   kills list). Read ONLY by DebriefingState (host-authoritative coop debrief) and the
	//   host-only-gated wasUnconcious (BattlescapeGame.cpp:1992, behind !coopThinClientNoReroll
	//   && getStunningImprovesMorale). No parallel-client mid-battle reader - the SAME class as
	//   the excluded `kills`. Excluding the parent map key drops the whole diary sub-tree.
	// motionPoints: the motion-scanner display accumulator (reset in prepareNewTurn:2942,
	//   accumulated per-machine during movement). next_turn DOES re-ship it
	//   (NextTurnState.cpp:681 -> setMotionPointsCoop), yet it still diverges at SIDESTART: the
	//   D-lite client's still-draining gated alien replay legitimately accumulates
	//   `_motionPoints` AFTER the next_turn overwrite. Serializing replay-before-apply is
	//   disproportionate for a motion-scanner DISPLAY value with no other reader -> the FOW /
	//   Option-B presentation carve-out class. PRESENTATION-EXCLUDE (manager sign-off, trace
	//   in prd-i3 ledger).
	return k == "AI" || k == "aiMedikitUsed" || k == "allocated"
		|| k == "visible"
		|| k == "turnsSinceSpotted"
		|| k == "turnsSinceSpottedByXcom"
		|| k == "turnsSinceSpottedByCivilian"
		|| k == "turnsLeftSpottedForSnipers"
		|| k == "turnsLeftSpottedForSnipersByXcom"
		|| k == "turnsLeftSpottedForSnipersByCivilian"
		|| k == "fatalShotSide"
		|| k == "fatalShotBodyPart"
		|| k == "murdererWeapon"
		|| k == "murdererWeaponAmmo"
		|| k == "murdererId"
		|| k == "kills"
		|| k == "notificationShown"
		|| k == "droppedOnAlienTurn"
		|| k == "turnsSinceStunned"
		|| k == "expBravery"
		|| k == "expReactions"
		|| k == "expFiring"
		|| k == "expThrowing"
		|| k == "expPsiSkill"
		|| k == "expPsiStrength"
		|| k == "expMana"
		|| k == "expMelee"
		|| k == "wantsToSurrender"
		|| k == "tempUnitStatistics"
		|| k == "motionPoints";
}

// PRD-I3 FOW contract (Option B, decided 2026-08-09): the per-tile
// "discovered"/FOW bits are presentation - derived locally from replicated
// positions, never promised identical between machines - so they are a permanent
// carve-out from the saveBlob hash, exactly as the fast `terrain` bucket already
// excludes them. They live packed inside the opaque binTiles base64 blob
// (Tile::saveBinary boolFields), which cannot be stripped by YAML node path, so
// decode the blob, zero the three discovered bits in every tile's boolFields byte,
// and feed the MASKED bytes to the hash (and its canonical-text twin). Everything
// else in the blob - the four mapDataID/setID pairs, smoke, fire, and the two
// ufo-door-open bits - is left byte-for-byte intact and still hashed, so real
// terrain / door / smoke / fire drift still lights the bucket.
//
// Layout anchored to Tile::saveBinary + the index prefix serialized in
// SavedBattleGame::save, sized by Tile::serializationKey (a compile-time constant,
// NOT versioned): each record is [index][mapDataID x4][mapDataSetID x4][smoke]
// [fire][boolFields], stride = serializationKey.totalBytes, boolFields last. In
// that byte (Tile::saveBinary): bit0 = O_WESTWALL.discovered,
// bit1 = O_NORTHWALL.discovered, bit2 = O_FLOOR.discovered (FOW, mask 0x07);
// bit3 = ufo-door-open west, bit4 = ufo-door-open north (KEEP).
bool saveBlobMaskFowBinTiles(const YAML::YamlNodeReader& node, std::vector<char>& out)
{
	out.clear();
	if (node.isMap() || node.isSeq()) return false; // binTiles is a scalar
	std::vector<char> bytes;
	try { bytes = node.readValBase64(); }
	catch (...) { return false; }
	const size_t stride = Tile::serializationKey.totalBytes;
	// boolFields sits after index + 4 mapDataID + 4 mapDataSetID + smoke + fire.
	const size_t boolOff = (size_t)Tile::serializationKey.index
		+ 4u * (size_t)Tile::serializationKey._mapDataID
		+ 4u * (size_t)Tile::serializationKey._mapDataSetID
		+ (size_t)Tile::serializationKey._smoke
		+ (size_t)Tile::serializationKey._fire;
	if (stride == 0 || boolOff >= stride) return false; // layout not as anchored
	const size_t records = bytes.size() / stride;
	for (size_t r = 0; r < records; ++r)
	{
		unsigned char& bf = reinterpret_cast<unsigned char&>(bytes[r * stride + boolOff]);
		bf = (unsigned char)(bf & (unsigned char)~0x07u); // clear FOW, keep ufo-door bits
	}
	out.swap(bytes);
	return true;
}

// Deterministic standard base64 (RFC 4648). The human-diffable saveBlob text twin
// renders the SAME masked binTiles bytes the hash consumes, so a dump diff stays
// faithful to the hash. Encoder only; decode is the engine's readValBase64.
std::string saveBlobBase64(const std::vector<char>& in)
{
	static const char T[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
	std::string out;
	out.reserve(((in.size() + 2) / 3) * 4);
	size_t i = 0;
	for (; i + 3 <= in.size(); i += 3)
	{
		unsigned n = ((unsigned)(unsigned char)in[i] << 16) | ((unsigned)(unsigned char)in[i + 1] << 8) | (unsigned char)in[i + 2];
		out += T[(n >> 18) & 63]; out += T[(n >> 12) & 63];
		out += T[(n >> 6) & 63];  out += T[n & 63];
	}
	if (i + 1 == in.size())
	{
		unsigned n = ((unsigned)(unsigned char)in[i] << 16);
		out += T[(n >> 18) & 63]; out += T[(n >> 12) & 63]; out += "==";
	}
	else if (i + 2 == in.size())
	{
		unsigned n = ((unsigned)(unsigned char)in[i] << 16) | ((unsigned)(unsigned char)in[i + 1] << 8);
		out += T[(n >> 18) & 63]; out += T[(n >> 12) & 63]; out += T[(n >> 6) & 63]; out += "=";
	}
	return out;
}

// Deterministic FNV-1a over the parsed node tree: keys and scalar values in
// document (= emit) order, recursing maps and sequences. Hashing the STRUCTURE of
// the re-parsed text (not the raw bytes) normalizes any whitespace/quoting
// difference between the two builds. @a top marks the battle map's own direct
// children, where the top-level-only exclusions apply.
void saveBlobHashTree(const YAML::YamlNodeReader& node, std::uint64_t& h, bool top)
{
	if (node.isMap())
	{
		for (const auto& child : node.children())
		{
			std::string_view key = child.key();
			if ((top && saveBlobExcludedTopKey(key)) || saveBlobExcludedAnyKey(key))
				continue;
			for (char ch : key) { h ^= (std::uint64_t)(unsigned char)ch; h *= FNV_PRIME; }
			// PRD-I3 FOW: hash the FOW-masked binTiles bytes, not the raw base64 scalar.
			std::vector<char> maskedTiles;
			if (key == "binTiles" && saveBlobMaskFowBinTiles(child, maskedTiles))
			{
				for (char b : maskedTiles) { h ^= (std::uint64_t)(unsigned char)b; h *= FNV_PRIME; }
				continue;
			}
			saveBlobHashTree(child, h, false);
		}
	}
	else if (node.isSeq())
	{
		for (const auto& child : node.children())
			saveBlobHashTree(child, h, false);
	}
	else
	{
		std::string_view val = node.val();
		for (char ch : val) { h ^= (std::uint64_t)(unsigned char)ch; h *= FNV_PRIME; }
	}
}

// PRD-I4 (test-only): the human-diffable twin of saveBlobHashTree - the SAME walk,
// the SAME exclusions, emitted as indented text. So when the saveBlob bucket goes
// red, a diff of the two machines' dumps names the field. Kept in step with
// saveBlobHashTree above (same key/seq/scalar order, same node skips).
void saveBlobCanonicalText(const YAML::YamlNodeReader& node, std::string& out,
						   int depth, bool top)
{
	const std::string pad(depth * 2, ' ');
	if (node.isMap())
	{
		for (const auto& child : node.children())
		{
			std::string_view key = child.key();
			if ((top && saveBlobExcludedTopKey(key)) || saveBlobExcludedAnyKey(key))
				continue;
			if (child.isMap() || child.isSeq())
			{
				out += pad; out.append(key.data(), key.size()); out += ":\n";
				saveBlobCanonicalText(child, out, depth + 1, false);
			}
			else
			{
				// PRD-I3 FOW: emit the SAME FOW-masked binTiles bytes the hash consumes,
				// so a dump diff stays consistent with the saveBlob hash.
				std::vector<char> maskedTiles;
				if (key == "binTiles" && saveBlobMaskFowBinTiles(child, maskedTiles))
				{
					out += pad; out.append(key.data(), key.size()); out += ": ";
					out += saveBlobBase64(maskedTiles); out += "\n";
				}
				else
				{
					std::string_view val = child.val();
					out += pad; out.append(key.data(), key.size()); out += ": ";
					out.append(val.data(), val.size()); out += "\n";
				}
			}
		}
	}
	else if (node.isSeq())
	{
		for (const auto& child : node.children())
		{
			if (child.isMap() || child.isSeq())
			{
				out += pad; out += "-\n";
				saveBlobCanonicalText(child, out, depth + 1, false);
			}
			else
			{
				std::string_view val = child.val();
				out += pad; out += "- "; out.append(val.data(), val.size()); out += "\n";
			}
		}
	}
	else
	{
		std::string_view val = node.val();
		out += pad; out.append(val.data(), val.size()); out += "\n";
	}
}

} // namespace

const char* battleHashBucketName(int i)
{
	return (i >= 0 && i < BATTLE_HASH_BUCKETS) ? BATTLE_HASH_NAMES[i] : "?";
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
	case 7: return h.unitsCombat;
	case 8: return h.unitsRegen;
	default: return 0;
	}
}

// PRD-I3 Session F: a debug-toggled REPORT-ONLY override. With all ten buckets promoted
// to ALARM there is no naturally report-only bucket left to carry test_sync_check's
// negative control (the proof that a report-only mismatch is logged + counted but does
// NOT latch the desync route). The TestServer `force_report_only` lever sets one of these
// true, forcing that bucket's alarm gate open for the control scenario. Index
// BATTLE_HASH_BUCKETS is saveBlob. Test-only; production never sets it, so it is inert.
bool g_battleHashReportOnlyOverride[BATTLE_HASH_BUCKETS + 1] = { false };

bool saveBlobAlarms()
{
	return SAVEBLOB_ALARM && !g_battleHashReportOnlyOverride[BATTLE_HASH_BUCKETS];
}

bool setBattleHashReportOnlyOverride(const std::string& name, bool on)
{
	for (int i = 0; i < BATTLE_HASH_BUCKETS; ++i)
		if (name == BATTLE_HASH_NAMES[i]) { g_battleHashReportOnlyOverride[i] = on; return true; }
	if (name == "saveBlob") { g_battleHashReportOnlyOverride[BATTLE_HASH_BUCKETS] = on; return true; }
	return false;
}

bool battleHashBucketAlarms(int i)
{
	if (i >= 0 && i < BATTLE_HASH_BUCKETS && g_battleHashReportOnlyOverride[i]) return false;
	return (i >= 0 && i < BATTLE_HASH_BUCKETS) && BATTLE_HASH_ALARM[i];
}

std::uint32_t battleHashLastSweepUs()
{
	return g_lastSweepUs;
}

/**
 * ONE sweep, seven buckets.
 *
 * Three loops - tiles, items, units - and a counter read. Every term is a SUM of
 * per-entity FNV-1a mixes rather than a rolling hash, for the reason the PRD-P2
 * terms already document: neither the tile array, nor `_items`, nor `_units` has
 * a replicated ORDER, so a term that depended on it would be a permanent red.
 *
 * FNV is spelled out rather than delegated to std::hash because the two machines
 * are not necessarily the same build (Windows .exe vs the Linux AppImage) and
 * std::hash is implementation-defined.
 */
bool computeBattleHashes(Game* game, BattleHashSet& out)
{
	out.terrain = out.fire = out.smoke = out.items = 0;
	out.unitsCore = out.unitsStats = out.itemIdCtr = 0;
	out.unitsCombat = out.unitsRegen = 0;
	if (!game || !game->getSavedGame()) return false;
	SavedBattleGame* battle = game->getSavedGame()->getSavedBattle();
	if (!battle) return false;

	const auto t0 = std::chrono::steady_clock::now();

	// --- tiles: terrain, fire, smoke ---------------------------------------
	//
	// terrain hashes the four TilePart map-data IDs, which is precisely what the
	// `destroy_tile` packet mutates on the peer (Tile::destroyCoop swaps the part
	// for its died-for object or clears it), plus the explosive accumulator that
	// packet also carries. NOT the animation frame, not the discovered/FOW bits:
	// the first is a display phase the two machines are never on the same frame
	// of, and the second is gated on a design decision PRD-I3 owns.
	//
	// A VOID tile contributes nothing at all, so the common case (open air above
	// the map) costs one branch. That is safe rather than merely fast: the skip is
	// a pure function of the tile's own state, so a tile that went void on ONE
	// machine is skipped there and mixed here, and the sums differ - which is the
	// detection we want.
	const int tileCount = battle->getMapSizeXYZ();
	for (int i = 0; i < tileCount; ++i)
	{
		Tile* tile = battle->getTile(i);
		if (!tile) continue;

		// NOT Tile::isVoid(): that also answers false for smoke and for a tile that
		// merely has an item lying on it, which would make `terrain` move whenever
		// `items` or `smoke` did - and a bucket that is not independent of its
		// neighbours cannot attribute anything. The skip here is map data only.
		bool hasPart = false;
		for (int part = 0; part < O_MAX && !hasPart; ++part)
		{
			hasPart = tile->getMapData((TilePart)part) != nullptr;
		}
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

		// The soak's `battle_tiles` census fields, which many clean runs have shown
		// to be equal at a side boundary - so they are a detector, not a red.
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
	}

	// --- items: the STRICT census ------------------------------------------
	// Wider than chkBattleCensus (which is id + type + owner): slot, tile
	// position and fuse are all replicated state, and each of them is a family of
	// drift the identity triple cannot see - an item in the wrong hand, an item
	// on the wrong floor tile, a grenade primed on one machine only.
	for (BattleItem* item : *battle->getItems())
	{
		if (!item) continue;
		std::uint64_t h = FNV_OFFSET;
		h = mix(h, item->getId());
		h ^= fnv1a(item->getRules() ? item->getRules()->getType() : std::string("?"));
		h *= FNV_PRIME;
		h = mix(h, item->getOwner() ? item->getOwner()->getId() : -1);
		h ^= fnv1a(item->getSlot() ? item->getSlot()->getId() : std::string("-"));
		h *= FNV_PRIME;
		h = mix(h, item->getSlotX());
		h = mix(h, item->getSlotY());
		const Tile* t = item->getTile();
		h = mix(h, t ? t->getPosition().x : -1);
		h = mix(h, t ? t->getPosition().y : -1);
		h = mix(h, t ? t->getPosition().z : -1);
		h = mix(h, item->getFuseTimer());
		out.items += h;
	}

	// --- units: core identity/liveness/position, then the full-fidelity stats --
	for (BattleUnit* unit : *battle->getUnits())
	{
		if (!unit) continue;
		const Position p = unit->getPosition();

		// EXACTLY the chkBattleUnits field set (id, faction, liveness, position),
		// reusing unitLiveness() so the two detectors can never disagree about what
		// "down" means.
		std::uint64_t c = FNV_OFFSET;
		c = mix(c, unit->getId());
		c = mix(c, (int)unit->getFaction());
		c = mix(c, unitLiveness(unit));
		c = mix(c, p.x);
		c = mix(c, p.y);
		c = mix(c, p.z);
		out.unitsCore += c;

		// The bucket PRD-I0 flags as expected-noisy, and the reason the split
		// exists: both machines regenerate TU, bleed fatal wounds and recover stun
		// in their OWN prepareNewTurn, so this term straddles state the protocol
		// repairs rather than replicates. It is here because it is also the term
		// that catches a cost charged on one machine only - which is the single
		// most common parallel-turns bug found so far (PRD-P9's legacy-packet cost
		// replication was exactly this). Report-only until PRD-I3 burns it in.
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
		const int* wounds = unit->getFatalWoundsCoop();
		for (int part = 0; part < BODYPART_MAX; ++part)
		{
			s = mix(s, wounds ? wounds[part] : 0);
		}
		out.unitsStats += s;

		// PRD-I3 SEAM-7/8/9: the SAME field set, SPLIT BY AUTHORSHIP into two independent
		// FNV sums so the compare can hold each field where its author makes it
		// well-defined:
		//   unitsCombat = CHAIN-authored ONLY (kneeled, mind-controller, w0..w5) -
		//     each written by an absolute the executor ships (kneel packet /
		//     mind-control / hit_unit's fatal-wound COUNTERS), so it is STRICT at every
		//     seq incl. ai/expl.
		//   unitsRegen = TURN-MACHINE / DEFERRED-authored (tu, energy, mana, morale, health,
		//     stun AND fire) - compared at SIDESTART only (syncCheckCompare).
		// SEAM-9 (manager sign-off 2026-08-12) moved HEALTH and STUN out of unitsCombat:
		// both machines bleed fatal wounds and recover stun in their OWN prepareNewTurn
		// (see the unitsStats note above), so health/stun straddle every per-action + endturn
		// sample exactly like tu/energy/mana/morale (trace: stun off-by-1 at ai/expl, health
		// bleed on downed units, all healed by next_turn). The wound COUNTERS stay in
		// unitsCombat - they are chain-authored (hit/medikit); only their BLEED CONSEQUENCE
		// on the health VALUE defers, and that value now rides unitsRegen.
		// FIRE (manager sign-off 2026-08-12) likewise moved to unitsRegen: getFire() is
		// chain-SET (unit_fire absolute) but turn-DECREMENTED in each machine's own
		// prepareNewTurn, so it straddles every per-action + endturn sample (incendiary
		// soak: unitsCombat 31-36 at ai/expl) and is well-defined only at sidestart -
		// identical dual authorship to health/stun/morale. The combined
		// unitsStats above is kept verbatim purely for the OLD-peer wire fallback.
		std::uint64_t comb = FNV_OFFSET;
		comb = mix(comb, unit->getId());
		comb = mix(comb, unit->isKneeled() ? 1 : 0);
		comb = mix(comb, unit->getMindControllerId());
		for (int part = 0; part < BODYPART_MAX; ++part)
		{
			comb = mix(comb, wounds ? wounds[part] : 0);
		}
		out.unitsCombat += comb;

		std::uint64_t regen = FNV_OFFSET;
		regen = mix(regen, unit->getId());
		regen = mix(regen, unit->getTimeUnits());
		regen = mix(regen, unit->getEnergy());
		regen = mix(regen, unit->getMana());
		regen = mix(regen, unit->getMorale()); // SEAM-8: morale is deferred-authored
		regen = mix(regen, unit->getHealth());     // SEAM-9: fatal-wound bleed defers
		regen = mix(regen, unit->getStunlevel());  // SEAM-9: stun recovery defers
		regen = mix(regen, unit->getFire());       // fire: chain-SET, turn-decremented (deferred)
		out.unitsRegen += regen;
	}

	out.itemIdCtr = (std::uint64_t)(std::int64_t)battle->getCurrentItemIdValue();

	g_lastSweepUs = (std::uint32_t)std::chrono::duration_cast<std::chrono::microseconds>(
		std::chrono::steady_clock::now() - t0).count();
	return true;
}

// ---- PRD-I3 SEAM-7: per-seq live unit-field dump + opt-in field-diff capture -------
//
// The unitsStats bucket is a SUM of FNV mixes: a mismatch names the bucket but never
// WHICH field of WHICH unit drifted, and the existing unit_stat_diff harness probe
// (battle_state.units) samples only tu/energy/health/stun/wounds/morale - NOT fire,
// kneeling, mana, mind-controller id or the six PER-PART fatal-wound counters, which
// are precisely the fields the bucket hashes that it cannot see. This builds the FULL
// bucket field vector per unit so a live dump (unit_stats_full lever) and an opt-in
// on-mismatch cross-machine diff can NAME the field. Introspection only.
bool g_syncFieldCapture = false;
void setSyncFieldCapture(bool on) { g_syncFieldCapture = on; }
bool syncFieldCapture() { return g_syncFieldCapture; }

void unitStatsFullJson(Game* game, Json::Value& out, int onlyId)
{
	out = Json::Value(Json::arrayValue);
	if (!game || !game->getSavedGame()) return;
	SavedBattleGame* battle = game->getSavedGame()->getSavedBattle();
	if (!battle) return;
	for (BattleUnit* unit : *battle->getUnits())
	{
		if (!unit) continue;
		if (onlyId >= 0 && unit->getId() != onlyId) continue;
		Json::Value u(Json::objectValue);
		u["id"] = unit->getId();
		// EXACTLY the computeBattleHashes() unitsStats field set, same order, so a
		// fieldDiffs readout explains a unitsStats bucket mismatch term for term.
		u["tu"] = unit->getTimeUnits();
		u["energy"] = unit->getEnergy();
		u["health"] = unit->getHealth();
		u["stun"] = unit->getStunlevel();
		u["morale"] = unit->getMorale();
		u["mana"] = unit->getMana();
		u["fire"] = unit->getFire();
		u["kneeled"] = unit->isKneeled() ? 1 : 0;
		u["mc"] = unit->getMindControllerId();
		const int* wounds = unit->getFatalWoundsCoop();
		for (int part = 0; part < BODYPART_MAX; ++part)
		{
			u["w" + std::to_string(part)] = wounds ? wounds[part] : 0;
		}
		out.append(u);
	}
}

// ---- PRD-I3 SEAM-3: per-seq terrain vector capture (introspection only) ------------
//
// The unit field-diff tooling above ships the client's full unit vector as `uv` on
// action_done, because a battle has a handful of units. The terrain equivalent cannot:
// a report would carry every non-void tile (up to 14400), on every action, doubling
// the action_done payload of a run - and it is armed exactly during the shot/destruction
// scenarios that already stress the transport (the mass-casualty WinError 10054 class).
// So this is INTROSPECTION ONLY, no wire change: when armed, BOTH machines stash their
// own full tile vector at the SAME sample computeBattleHashes() took, into a bounded
// local ring, and the harness reads BOTH rings for the mismatching seq (which the host
// already names in syncCheck.mismatches) and diffs them offline. OFF by default = the
// capture-off path is byte-identical (one bool test at each hash point).
bool g_syncTerrainCapture = false;
void setSyncTerrainCapture(bool on) { g_syncTerrainCapture = on; }
bool syncTerrainCapture() { return g_syncTerrainCapture; }

// One tile's terrain-bucket fields (compact - a Json::Value per tile would be an order
// of magnitude of memory for a full-map ring). `doorBits` is DIAGNOSTIC only: the bucket
// does NOT hash UFO-door open state (it lives in Tile::_objectsCache[part].currentFrame,
// not in the map-data id/set-id the bucket reads - VERIFY-1), so it is captured here to
// make a door divergence VISIBLE to the offline diff even though it never moves `terrain`.
struct TerrainTileRec
{
	std::int32_t index;
	std::int32_t m[O_MAX];   ///< mapDataID per part
	std::int32_t s[O_MAX];   ///< mapDataSetID per part
	std::int32_t explosive;
	std::int32_t explosiveType;
	// DIAGNOSTIC per-part door flags (NONE of these are in the terrain bucket) - 3 bits
	// per part: isDoor(3p) / isUfoDoor(3p+1) / isUfoDoorOpen(3p+2). Captured at HASH time
	// so the diff can tell a DOOR straddle (the lagging machine still holds a CLOSED door -
	// isDoor set - while the other holds the opened leaf) from DESTRUCTION (isDoor clear on
	// both, only the map-data id moves).
	std::uint16_t doorBits;
};
struct TerrainCaptureEntry
{
	bool boundary;
	std::uint32_t seq;
	std::uint32_t sideSeq;
	std::string kind;
	std::vector<TerrainTileRec> tiles;
};
// Bounded like the sync ring: only the last few seqs matter for a live mismatch diff.
const size_t TERRAIN_CAPTURE_MAX = 48;
std::deque<TerrainCaptureEntry> g_terrainCaptureRing;

// The INCLUSION TEST here MUST match computeBattleHashes()'s terrain loop exactly (a tile
// with any map-data part OR a non-zero explosive), so the captured vector reproduces the
// bucket hash the compare fired on. @a onlyIndex >= 0 narrows to one tile.
static void buildTerrainVec(SavedBattleGame* battle, std::vector<TerrainTileRec>& out, int onlyIndex)
{
	out.clear();
	if (!battle) return;
	const int tileCount = battle->getMapSizeXYZ();
	for (int i = 0; i < tileCount; ++i)
	{
		if (onlyIndex >= 0 && i != onlyIndex) continue;
		Tile* tile = battle->getTile(i);
		if (!tile) continue;
		bool hasPart = false;
		for (int part = 0; part < O_MAX && !hasPart; ++part)
			hasPart = tile->getMapData((TilePart)part) != nullptr;
		if (!(hasPart || tile->getExplosive() != 0)) continue;
		TerrainTileRec r;
		r.index = i;
		r.doorBits = 0;
		for (int part = 0; part < O_MAX; ++part)
		{
			int mid = -1, sid = -1;
			tile->getMapData(&mid, &sid, (TilePart)part);
			r.m[part] = mid;
			r.s[part] = sid;
			if (tile->isDoor((TilePart)part))       r.doorBits |= (std::uint16_t)(1u << (3 * part + 0));
			if (tile->isUfoDoor((TilePart)part))    r.doorBits |= (std::uint16_t)(1u << (3 * part + 1));
			if (tile->isUfoDoorOpen((TilePart)part)) r.doorBits |= (std::uint16_t)(1u << (3 * part + 2));
		}
		r.explosive = tile->getExplosive();
		r.explosiveType = tile->getExplosiveType();
		out.push_back(r);
		if (onlyIndex >= 0) break;
	}
}

static void terrainVecToJson(const std::vector<TerrainTileRec>& v, Json::Value& out)
{
	out = Json::Value(Json::arrayValue);
	for (const auto& r : v)
	{
		Json::Value t(Json::objectValue);
		t["i"] = r.index;
		for (int p = 0; p < O_MAX; ++p)
		{
			t["m" + std::to_string(p)] = r.m[p];
			t["s" + std::to_string(p)] = r.s[p];
		}
		t["expl"] = r.explosive;
		t["explType"] = r.explosiveType;
		t["door"] = (int)r.doorBits;
		out.append(t);
	}
}

void tileTerrainFullJson(Game* game, Json::Value& out, int onlyIndex)
{
	out = Json::Value(Json::arrayValue);
	if (!game || !game->getSavedGame()) return;
	SavedBattleGame* battle = game->getSavedGame()->getSavedBattle();
	if (!battle) return;
	std::vector<TerrainTileRec> v;
	buildTerrainVec(battle, v, onlyIndex);
	terrainVecToJson(v, out);
}

// Capture this machine's full terrain vector for a recorded seq. Called from
// syncCheckRecord (host ring point) and syncCheckAttach (client emit point) so both
// sides stash the SAME sample their bucket hash was computed from. No-op unless armed.
static void terrainCaptureRecord(Game* game, std::uint32_t seq, std::uint32_t sideSeq,
								 bool boundary, const std::string& kind)
{
	if (!g_syncTerrainCapture) return;
	if (!game || !game->getSavedGame()) return;
	SavedBattleGame* battle = game->getSavedGame()->getSavedBattle();
	if (!battle) return;
	TerrainCaptureEntry e;
	e.boundary = boundary;
	e.seq = seq;
	e.sideSeq = boundary ? 0 : sideSeq;
	e.kind = kind;
	buildTerrainVec(battle, e.tiles, -1);
	while (g_terrainCaptureRing.size() >= TERRAIN_CAPTURE_MAX)
		g_terrainCaptureRing.pop_front();
	g_terrainCaptureRing.push_back(std::move(e));
}

bool terrainCaptureDumpJson(std::uint32_t seq, bool boundary, int sideSeq, Json::Value& out)
{
	// Newest match wins: a per-side action seq recycles every side, and the newest
	// entry with this seq belongs to the current side (the one a live mismatch is on).
	for (auto it = g_terrainCaptureRing.rbegin(); it != g_terrainCaptureRing.rend(); ++it)
	{
		if (it->boundary != boundary || it->seq != seq) continue;
		if (sideSeq >= 0 && !boundary && it->sideSeq != (std::uint32_t)sideSeq) continue;
		out["seq"] = (Json::UInt)it->seq;
		out["side_seq"] = (Json::UInt)it->sideSeq;
		out["boundary"] = it->boundary;
		out["kind"] = it->kind;
		out["tileCount"] = (Json::UInt)it->tiles.size();
		terrainVecToJson(it->tiles, out["tiles"]);
		return true;
	}
	return false;
}

void terrainCaptureSeqsJson(Json::Value& out)
{
	out = Json::Value(Json::arrayValue);
	for (const auto& e : g_terrainCaptureRing)
	{
		Json::Value j(Json::objectValue);
		j["seq"] = (Json::UInt)e.seq;
		j["side_seq"] = (Json::UInt)e.sideSeq;
		j["boundary"] = e.boundary;
		j["kind"] = e.kind;
		j["tileCount"] = (Json::UInt)e.tiles.size();
		out.append(j);
	}
}

/**
 * PRD-I2: the save-derived boundary hash - the coverage backstop.
 *
 * Serializes the battle EXACTLY as a save would (the self-contained
 * SavedBattleGame::save writer, into memory, never disk), strips a short
 * machine-local exclusion list by node path, and FNV-1a hashes the canonical
 * tree. The seven sweep buckets certify the fields we enumerated; this certifies
 * the ones we forgot, and tracks the engine automatically as `save` evolves.
 *
 * Cost is the serialization (est. 5-20 ms), which is why it runs ONLY at the two
 * side boundaries and never per action. Measured into g_lastSaveBlobUs.
 */
bool computeSaveBlobHash(Game* game, std::uint64_t& out)
{
	out = 0;
	if (!game || !game->getSavedGame()) return false;
	SavedBattleGame* battle = game->getSavedGame()->getSavedBattle();
	if (!battle) return false;

	const auto t0 = std::chrono::steady_clock::now();

	// Battle document ONLY (separable: SavedBattleGame::save is self-contained), so
	// none of the geoscape / session / RNG state a full SavedGame::save would drag
	// in is ever hashed - it is authority-local or role-relative by construction.
	YAML::YamlRootNodeWriter writer;
	writer.setAsMap();
	battle->save(writer["battle"]);
	YAML::YamlString text = writer.emit();

	// Re-parse and hash the STRUCTURE, so the exclusion list applies on the node
	// tree (PRD-I2 2) and emit-formatting differences between the two builds cannot
	// register as a divergence.
	YAML::YamlRootNodeReader reader(text, "saveBlob");
	std::uint64_t h = FNV_OFFSET;
	saveBlobHashTree(reader["battle"], h, true);
	out = h;

	g_lastSaveBlobUs = (std::uint32_t)std::chrono::duration_cast<std::chrono::microseconds>(
		std::chrono::steady_clock::now() - t0).count();
	return true;
}

bool computeSaveBlobText(Game* game, std::string& out)
{
	out.clear();
	if (!game || !game->getSavedGame()) return false;
	SavedBattleGame* battle = game->getSavedGame()->getSavedBattle();
	if (!battle) return false;

	// The same serialization computeSaveBlobHash hashes: the self-contained battle
	// document, in memory, re-parsed so emit formatting cannot register as content.
	YAML::YamlRootNodeWriter writer;
	writer.setAsMap();
	battle->save(writer["battle"]);
	YAML::YamlString text = writer.emit();
	YAML::YamlRootNodeReader reader(text, "saveBlob");
	saveBlobCanonicalText(reader["battle"], out, 0, true);
	return true;
}

std::uint32_t battleHashLastSaveBlobUs()
{
	return g_lastSaveBlobUs;
}

void syncCheckRecord(Game* game, std::uint32_t seq, std::uint32_t sideSeq,
					 bool boundary, const std::string& kind)
{
	SyncRingEntry e;
	e.boundary = boundary;
	e.seq = seq;
	e.sideSeq = boundary ? 0 : sideSeq;
	e.kind = kind;
	e.compared = false;
	if (!computeBattleHashes(game, e.h)) return; // no battle: nothing to remember
	// PRD-I2: the save-derived hash is boundary-only. Per-action entries keep
	// e.saveBlob at 0 and never ship the field, so it is compared only at
	// boundaries; recorded here so the peer's boundary report has a match.
	if (boundary) computeSaveBlobHash(game, e.saveBlob);
	// PRD-I3 SEAM-7: stash this machine's full unitsStats field vector (opt-in), the
	// SAME sample e.h was computed from, for a field-by-field mismatch diff later.
	if (g_syncFieldCapture) unitStatsFullJson(game, e.statVec, -1);
	// PRD-I3 SEAM-3: HOST-side terrain vector capture (opt-in), same sample as e.h.
	terrainCaptureRecord(game, seq, sideSeq, boundary, kind);

	while (g_syncRing.size() >= SYNC_RING_MAX)
	{
		// PRD-I0 §3: overflow drops the OLDEST, with a log. Only an entry that was
		// never answered is worth a line - evicting a compared one is the ring
		// doing its job.
		if (!g_syncRing.front().compared)
		{
			++g_syncDropped;
			Log(LOG_WARNING) << "[COOP] SYNC-CHECK ring overflow: dropping uncompared seq "
							 << g_syncRing.front().seq
							 << (g_syncRing.front().boundary ? " (boundary)" : "")
							 << " kind=" << g_syncRing.front().kind
							 << " - the peer has stopped reporting hashes";
		}
		g_syncRing.pop_front();
	}
	g_syncRing.push_back(e);
	if (boundary) g_syncLastBoundarySeq = seq;
	else g_syncLastSeq = seq;
}

void syncCheckAttach(Game* game, Json::Value& msg)
{
	BattleHashSet h;
	if (!computeBattleHashes(game, h)) return;
	Json::Value node(Json::objectValue);
	for (int i = 0; i < BATTLE_HASH_BUCKETS; ++i)
	{
		node[BATTLE_HASH_NAMES[i]] = static_cast<Json::UInt64>(battleHashBucketValue(h, i));
	}
	msg["h"] = node;
	// PRD-I3 Session F: flag a report whose hash was sampled while THIS machine's death
	// replay has not converted its corpse yet. The item terms + saveBlob are then one
	// death behind the executor's ring entry (the corpse exists on the host, not here),
	// so the host skips those buckets for this report - the SAME rule verifyBattleChecksum
	// applies to the P2 tripwire (corpseReplayPendingAny). Additive; an old host ignores it.
	// PRD-I3 SEAM-11: a projectile replay in flight (_coopInitDeath) means this machine's
	// DISPLAY replay is still running spendAmmoForAction, so a fired clip's ammoqty is
	// transiently below the next_turn absolute (the display animation lags past the turn
	// boundary on a backlogged client) - the SAME display-lag class as a pending corpse.
	// Reuse the flag: the host skips items/itemIdCtr (harmless - a plain shot mints nothing)
	// and, the point here, saveBlob, for this report; the next boundary compares them
	// settled once the replay drains and next_turn re-ships the ammo absolute.
	const bool coopDisplayReplay = game->getCoopMod() && game->getCoopMod()->_coopInitDeath;
	if (corpseReplayPendingAny() || corpseRemapPendingAny() || coopDisplayReplay) msg["corpsePending"] = true;
	// PRD-I3 SEAM-7 (opt-in): the full per-unit field vector, sampled in the SAME pass
	// as `h`, so the host can diff a unitsStats mismatch field-by-field. Absent unless
	// the capture toggle is armed (zero wire delta by default; an old/normal peer never
	// sends it, and the host presence-gates on it).
	if (g_syncFieldCapture) unitStatsFullJson(game, msg["uv"], -1);
	// PRD-I3 SEAM-3: CLIENT-side terrain vector capture (opt-in, introspection only - NOT
	// shipped in msg). Same sample as `h`, stashed in this machine's local ring keyed by
	// the seq the outgoing action_done carries, so the harness can pull it back and diff
	// it against the host's ring entry for the same seq. Boundary reports carry `bseq`.
	if (g_syncTerrainCapture)
	{
		const bool boundary = msg.get("boundary", false).asBool();
		const std::uint32_t seq = boundary
			? static_cast<std::uint32_t>(msg.get("bseq", 0).asUInt())
			: static_cast<std::uint32_t>(msg.get("seq", 0).asUInt());
		const std::uint32_t sideSeq = static_cast<std::uint32_t>(msg.get("side_seq", 0).asUInt());
		terrainCaptureRecord(game, seq, sideSeq, boundary, std::string());
	}
}

void syncCheckAttachBoundary(Game* game, Json::Value& msg)
{
	// The seven fast sweep buckets first (identical to a per-action report)...
	syncCheckAttach(game, msg);
	if (!msg.isMember("h")) return; // no live battle
	// ...then the boundary-only save-derived bucket. Its PRESENCE in the "h" map is
	// what gates the host compare: a per-action report never carries it and an old
	// peer never carries it, so both are skipped without any policy flag.
	std::uint64_t blob = 0;
	if (computeSaveBlobHash(game, blob))
		msg["h"]["saveBlob"] = static_cast<Json::UInt64>(blob);
}

// PRD-I3 SEAM-7: diff the two machines' full unit-field vectors (host ring entry vs
// peer `uv`) and record/log each disagreeing (unit, field, host, peer). Called only
// when a unitsStats bucket term mismatched AND both vectors are present (capture on).
static void recordSeam7FieldDiffs(const Json::Value& hostUv, const Json::Value& peerUv,
	std::uint32_t seq, bool boundary, const std::string& kind)
{
	std::map<int, Json::Value> peerById;
	for (Json::ArrayIndex i = 0; i < peerUv.size(); ++i)
	{
		const Json::Value& pu = peerUv[i];
		if (pu.isObject() && pu.isMember("id")) peerById[pu["id"].asInt()] = pu;
	}
	for (Json::ArrayIndex i = 0; i < hostUv.size(); ++i)
	{
		const Json::Value& hu = hostUv[i];
		if (!hu.isObject() || !hu.isMember("id")) continue;
		int id = hu["id"].asInt();
		auto it = peerById.find(id);
		if (it == peerById.end()) continue;
		const Json::Value& pu = it->second;
		for (const auto& key : hu.getMemberNames())
		{
			if (key == "id") continue;
			if (!pu.isMember(key)) continue;
			const std::int64_t hv = hu[key].asInt64();
			const std::int64_t pv = pu[key].asInt64();
			if (hv == pv) continue;
			if (g_syncFieldDiffs.size() >= SYNC_FIELDDIFF_MAX) g_syncFieldDiffs.pop_front();
			SyncFieldDiff d;
			d.seq = seq; d.boundary = boundary; d.kind = kind;
			d.unitId = id; d.field = key; d.host = hv; d.peer = pv;
			g_syncFieldDiffs.push_back(d);
			Log(LOG_WARNING) << "[COOP][SEAM7] unitsStats field diff seq=" << seq
				<< (boundary ? " (boundary)" : "") << " kind=" << (kind.empty() ? "?" : kind)
				<< " unit=" << id << " field=" << key << " host=" << hv << " peer=" << pv;
		}
	}
}

void syncCheckCompare(Game* game, const Json::Value& msg)
{
	if (!msg.isMember("h")) return; // older peer: additive field absent = skip
	const Json::Value& node = msg["h"];
	if (!node.isObject()) return;

	const bool boundary = msg.get("boundary", false).asBool();
	const std::uint32_t seq = boundary
		? static_cast<std::uint32_t>(msg.get("bseq", 0).asUInt())
		: static_cast<std::uint32_t>(msg.get("seq", 0).asUInt());
	const std::uint32_t sideSeq = static_cast<std::uint32_t>(msg.get("side_seq", 0).asUInt());
	if (seq == 0) return;
	// PRD-I3 Session F: the reporting machine's death replay had not minted its corpse when
	// it sampled this hash, so the item terms + saveBlob are one death behind here. Mirrors
	// verifyBattleChecksum's corpseReplayPendingAny skip. Present-gated (old peer never sets it).
	const bool corpsePending = msg.get("corpsePending", false).asBool();

	SyncRingEntry* entry = nullptr;
	for (auto& e : g_syncRing)
	{
		// SUBSUMPTION. The client's report carries `_clientDisplaySeq`, which is
		// allowed to JUMP (a parked report released by the test hold lever, or two
		// markers consumed before an emit) - and when it does, its hash is the state
		// after ALL of the chains it skipped, so those entries can never get an
		// answer of their own. Closing them out here is not a fudge: it is what
		// stops the ring's overflow warning - "the peer has stopped reporting" -
		// from firing on chains the peer answered collectively.
		if (e.boundary == boundary && !e.compared && e.seq < seq
			&& (boundary || e.sideSeq == sideSeq))
		{
			e.compared = true;
		}
		// `action_seq` restarts at 0 every side, so the ACTION namespace is keyed
		// on (side_seq, seq); the boundary namespace is monotonic per battle and
		// needs no side. Without the side term a report that crossed a boundary in
		// flight would be compared against a brand-new chain that happens to carry
		// the same low seq - i.e. a guaranteed false red once a side.
		if (e.boundary == boundary && e.seq == seq
			&& (boundary || e.sideSeq == sideSeq))
		{
			entry = &e;
			break;
		}
	}
	if (!entry)
	{
		++g_syncStaleReports;
		return;
	}
	entry->compared = true;
	++g_syncCompares;
	++g_syncKindCompares[entry->kind.empty() ? std::string("?") : entry->kind];
	// FOLLOW rather than max: the action namespace restarts at 0 every side, so a
	// max would leave the watermark stuck on the previous side's highest seq and
	// "the loop has closed" would never be false again.
	if (boundary) g_syncLastComparedBoundarySeq = seq;
	else g_syncLastComparedSeq = seq;

	// PRD-I3 SEAM-7: a peer that shipped the SPLIT buckets supersedes the combined
	// unitsStats - compare the split, skip the combined (which still carries the
	// straddle the split legitimately excludes). Absent split = OLD peer = fall back
	// to the combined below (presence-gated, bidirectional).
	const bool hasSplit = node.isMember("unitsCombat") || node.isMember("unitsRegen");
	bool seam7Recorded = false;
	bool alarm = false;
	for (int i = 0; i < BATTLE_HASH_BUCKETS; ++i)
	{
		const char* name = BATTLE_HASH_NAMES[i];
		if (!node.isMember(name)) continue; // a peer that predates this bucket
		if (std::strcmp(name, "unitsStats") == 0 && hasSplit)
			continue; // superseded by unitsCombat/unitsRegen (this peer shipped the split)
		// PRD-I3 SEAM-2 HALF 1: EXCLUDE the smoke/fire hazard buckets from an ENDTURN
		// boundary comparison - the endturn hazard sample is ill-defined (all decay
		// runs once per cycle at neutral->player, AFTER both endturn boundaries are
		// armed, and the host flushes the endturn boundary racing its own decay). The
		// SIDESTART boundary keeps them (hash-after-apply of next_turn = well-defined).
		// The client still ships every bucket in `h`; only this host-side compare skips
		// them, so the wire is unchanged and old/new peers stay symmetric. A skipped
		// bucket is NOT counted as compared.
		const bool hazardBucket =
			std::strcmp(name, "smoke") == 0 || std::strcmp(name, "fire") == 0;
		if (boundary && hazardBucket && entry->kind == "endturn")
		{
			++g_syncEndturnHazardSkips;
			continue;
		}
		// PRD-I3 SEAM-9 (manager sign-off 2026-08-12): the unitsRegen (turn-machine/
		// DEFERRED-authored) bucket - tu/energy/mana/morale AND health/stun - is well-defined
		// ONLY at SIDESTART (hash-after-apply of next_turn). During a side both machines
		// advance it in their own prepareNewTurn / defer it under D-lite, so EVERY per-action
		// seq (ai, expl, player) AND the endturn boundary straddle it (traced: stun off-by-1
		// at ai/expl, morale at player seqs, downed-unit health bleed - all healed by
		// sidestart, none ever firing at sidestart). Compare at sidestart ONLY; skip
		// elsewhere. saveBlob (whole-save superset) and the strict chain-authored unitsCombat
		// keep the per-action coverage. A skipped bucket is NOT counted as compared.
		if (std::strcmp(name, "unitsRegen") == 0)
		{
			if (!(boundary && entry->kind == "sidestart"))
			{
				if (boundary && entry->kind == "endturn") ++g_syncRegenEndturnSkips;
				else ++g_syncRegenAiSkips; // per-action (ai/expl/player) + neutral deferred skip
				continue;
			}
		}
		// PRD-I3 unitsCore side-gate (2026-08-14, Session C, manager sign-off after the
		// field-level trace): the core bucket (id/faction/liveness/position) is well-
		// defined at PLAYER-side per-action seqs and at SIDESTART, but NOT during the
		// ALIEN side. There the D-lite client replays the host's alien turn one step
		// behind its authoritative resolution, so a unit mid death/knockback/stun-
		// collapse (ai/expl per-action seqs) and at the alien-side ENDTURN boundary
		// transiently diverges in liveness/position - traced 2026-08-14: a full multi-
		// packet explosion/casualty resolution differs (e.g. host health 33 / peer 0,
		// direction varying, several units at once), always healing by sidestart/
		// next_turn. Skip the alien per-action seqs AND the endturn boundary; keep
		// player-side per-action (strict) + sidestart, where a PERSISTENT alien-side
		// desync still surfaces. Mirrors the SEAM-9 unitsRegen sidestart discipline but
		// keeps the player-side coverage that is the point of a strict liveness/position
		// bucket. A skipped bucket is NOT counted as compared.
		if (std::strcmp(name, "unitsCore") == 0)
		{
			const bool alienSeq = !boundary && (entry->kind == "ai" || entry->kind == "expl");
			const bool endturnBnd = boundary && entry->kind == "endturn";
			if (alienSeq || endturnBnd)
			{
				if (endturnBnd) ++g_syncCoreEndturnSkips;
				else ++g_syncCoreAlienSkips;
				continue;
			}
		}
		// PRD-I3 terrain side-gate (2026-08-14, Session E): SAME discipline as unitsCore.
		// The SEAM-3 loose-destroy chokepoint closed the in-chain leak, but a residual
		// destroy_tile mapDataID still lands one step behind the host's authoritative
		// destruction during the alien-side AI/explosion replay (kind ai/expl) and at the
		// alien-side ENDTURN boundary, healing by sidestart (traced Session E: terrain
		// ai/endturn only, never a player seq, never sidestart). Skip the alien per-action
		// seqs + endturn; keep player-side per-action (strict) + sidestart, where a
		// PERSISTENT terrain divergence still surfaces. A skipped bucket is NOT compared.
		if (std::strcmp(name, "terrain") == 0)
		{
			const bool alienSeq = !boundary && (entry->kind == "ai" || entry->kind == "expl");
			const bool endturnBnd = boundary && entry->kind == "endturn";
			if (alienSeq || endturnBnd)
			{
				if (endturnBnd) ++g_syncTerrainEndturnSkips;
				else ++g_syncTerrainAlienSkips;
				continue;
			}
		}
		// PRD-I3 Session F items/itemIdCtr side-gate (2026-08-15, manager sign-off): SAME
		// discipline as terrain/unitsCore (see the note by g_syncItemsAlienSkips). The residual
		// drift is the ALIEN-side display window - the D-lite client's gated alien replay lags
		// the host's authoritative corpse resolution (ai/expl seqs + alien-side endturn),
		// healing by sidestart. The BOUNDARY-death corpse mint is covered by the P4
		// after_unit_death manifest (proven lockstep). Skip alien per-action + endturn; keep
		// player-side per-action (strict) + sidestart, where a persistent drift still surfaces
		// AND the items player-seq negative control still sees its mint. NOT counted as compared.
		if (std::strcmp(name, "items") == 0 || std::strcmp(name, "itemIdCtr") == 0)
		{
			const bool alienSeq = !boundary && (entry->kind == "ai" || entry->kind == "expl");
			const bool endturnBnd = boundary && entry->kind == "endturn";
			if (alienSeq || endturnBnd)
			{
				if (endturnBnd) ++g_syncItemsEndturnSkips;
				else ++g_syncItemsAlienSkips;
				continue;
			}
			// The reporting machine's corpse mint was still in flight (mirrors the P2
			// tripwire): the item terms are one death behind, heal on the next report.
			if (corpsePending)
			{
				++g_syncItemsCorpsePendingSkips;
				continue;
			}
		}
		++g_syncBucketCompares[i];
		if (boundary && hazardBucket && entry->kind == "sidestart")
			++g_syncSidestartHazardCompares;
		const std::uint64_t peer = static_cast<std::uint64_t>(node[name].asUInt64());
		const std::uint64_t mine = battleHashBucketValue(entry->h, i);
		if (peer == mine) continue;

		++g_syncBucketMismatches[i];
		if (g_syncMismatches.size() >= SYNC_MISMATCH_MAX) g_syncMismatches.pop_front();
		SyncMismatch m;
		m.seq = seq;
		m.boundary = boundary;
		m.kind = entry->kind;
		m.bucket = name;
		g_syncMismatches.push_back(m);

		Log(LOG_ERROR) << "[COOP] SYNC-CHECK MISMATCH seq=" << seq
					   << (boundary ? " (boundary)" : "")
					   << " kind=" << (entry->kind.empty() ? "?" : entry->kind)
					   << " bucket=" << name
					   << " host=" << mine << " peer=" << peer
					   << (battleHashBucketAlarms(i) ? " [ALARM]" : " [report-only]");
		if (battleHashBucketAlarms(i)) alarm = true;

		// PRD-I3 SEAM-7: name the exact field(s) behind a unit-stats mismatch (combined
		// OR either split bucket), once per compare, when the opt-in capture rode both
		// this report (`uv`) and this ring entry.
		const bool unitFamily = std::strcmp(name, "unitsStats") == 0
			|| std::strcmp(name, "unitsCombat") == 0
			|| std::strcmp(name, "unitsRegen") == 0;
		if (unitFamily && !seam7Recorded && entry->statVec.isArray()
			&& msg.isMember("uv") && msg["uv"].isArray())
		{
			recordSeam7FieldDiffs(entry->statVec, msg["uv"], seq, boundary, entry->kind);
			seam7Recorded = true;
		}
	}

	// PRD-I2: the boundary-only save-derived bucket. Presence-gated exactly like
	// the seven above - only a boundary report from a current-build peer carries
	// `saveBlob`, and the host recorded entry->saveBlob only for boundary entries.
	if (node.isMember("saveBlob"))
	{
		// PRD-I3 saveBlob endturn straddle: SIDESTART-only compare. At an endturn
		// boundary the whole-save hash straddles the deferred turn-machine state the
		// D-lite client resolves only at next_turn, so the endturn saveBlob sample is
		// ill-defined; SIDESTART (hash-after-apply of next_turn) is the well-defined
		// point. Mirrors the SEAM-2 HALF-1 smoke/fire endturn skip - compare-site only.
		const bool saveBlobEndturn = boundary && entry->kind == "endturn";
		// PRD-I3 Session F: the whole-save superset includes the item census, so a corpse
		// mint still in flight on the reporting machine straddles saveBlob too - skip it the
		// same way (mirrors verifyBattleChecksum). Heals on the next boundary.
		if (saveBlobEndturn) ++g_syncSaveBlobEndturnSkips;
		else if (corpsePending) ++g_syncSaveBlobCorpsePendingSkips;
		else if (boundary && entry->kind == "sidestart") ++g_syncSaveBlobSidestartCompares;
		const std::uint64_t peer = static_cast<std::uint64_t>(node["saveBlob"].asUInt64());
		const std::uint64_t mine = entry->saveBlob;
		if (!saveBlobEndturn && !corpsePending && peer != mine)
		{
			++g_syncSaveBlobMismatches;
			if (g_syncMismatches.size() >= SYNC_MISMATCH_MAX) g_syncMismatches.pop_front();
			SyncMismatch m;
			m.seq = seq;
			m.boundary = boundary;
			m.kind = entry->kind;
			m.bucket = "saveBlob";
			g_syncMismatches.push_back(m);
			Log(LOG_ERROR) << "[COOP] SYNC-CHECK MISMATCH seq=" << seq
						   << (boundary ? " (boundary)" : "")
						   << " kind=" << (entry->kind.empty() ? "?" : entry->kind)
						   << " bucket=saveBlob host=" << mine << " peer=" << peer
						   << (saveBlobAlarms() ? " [ALARM]" : " [report-only]");
			if (saveBlobAlarms()) alarm = true;
		}
	}

	if (!alarm) return;

	// ALARM route: the SAME path the PRD-P2 tripwire takes, deliberately - one
	// latch, one banner, one bundle, whichever detector spoke.
	g_battleDesyncSeen = true;
	// PRD-I4: an ALARM-promoted bucket triggers the diagnostic bundle here, the
	// same as the P2 tripwire (latched to one per battle). Today every bucket is
	// REPORT-ONLY (BATTLE_HASH_ALARM all false), so promotion alone arms this - no
	// further code change. The attribution comes from the sync-check's own last
	// mismatch (buildDesyncInfo -> desyncComputeAttribution reads g_syncMismatches).
	{
		DesyncTerms report;
		battleChecksumTerms(game, report.localItemId, report.localCensus, report.localUnits);
		report.context = "sync_check";
		captureDesyncReport(game, report);
	}
	SavedBattleGame* battle = game && game->getSavedGame()
		? game->getSavedGame()->getSavedBattle() : nullptr;
	const std::int64_t nowMs = steadyMs();
	if (g_lastBattleNotifyMs >= 0 && nowMs - g_lastBattleNotifyMs < RESYNC_DEBOUNCE_MS) return;
	g_lastBattleNotifyMs = nowMs;
	if (battle)
	{
		if (BattlescapeState* bs = battle->getBattleState())
		{
			bs->warningLongRaw("CO-OP DESYNC DETECTED - SEE openxcom.log");
		}
	}
}

void syncCheckReport(Json::Value& out)
{
	Json::Value node(Json::objectValue);
	node["lastSeq"] = static_cast<Json::UInt>(g_syncLastSeq);
	node["lastComparedSeq"] = static_cast<Json::UInt>(g_syncLastComparedSeq);
	node["lastBoundarySeq"] = static_cast<Json::UInt>(g_syncLastBoundarySeq);
	node["lastComparedBoundarySeq"] = static_cast<Json::UInt>(g_syncLastComparedBoundarySeq);
	node["ringDepth"] = static_cast<Json::UInt>(g_syncRing.size());
	node["compares"] = static_cast<Json::UInt64>(g_syncCompares);
	node["staleReports"] = static_cast<Json::UInt64>(g_syncStaleReports);
	node["dropped"] = static_cast<Json::UInt64>(g_syncDropped);
	node["sweepUs"] = static_cast<Json::UInt>(g_lastSweepUs);
	Json::Value kinds(Json::objectValue);
	for (const auto& kv : g_syncKindCompares)
	{
		kinds[kv.first] = static_cast<Json::UInt64>(kv.second);
	}
	node["comparedKinds"] = kinds;
	// PRD-I3 SEAM-2 HALF 1: the endturn hazard exclusion + the sidestart hazard
	// compares, so a test can assert smoke/fire are UNCOMPARED at endturn but still
	// compared (and equal) at sidestart.
	node["endturnHazardSkips"] = static_cast<Json::UInt64>(g_syncEndturnHazardSkips);
	node["sidestartHazardCompares"] = static_cast<Json::UInt64>(g_syncSidestartHazardCompares);
	// PRD-I3 SEAM-7: unitsRegen straddle exclusions (ai-seq + endturn boundary), so a
	// test can assert unitsRegen was skipped exactly at the straddle window.
	node["unitsRegenAiSkips"] = static_cast<Json::UInt64>(g_syncRegenAiSkips);
	node["unitsRegenEndturnSkips"] = static_cast<Json::UInt64>(g_syncRegenEndturnSkips);
	node["unitsCoreAlienSkips"] = static_cast<Json::UInt64>(g_syncCoreAlienSkips);
	node["unitsCoreEndturnSkips"] = static_cast<Json::UInt64>(g_syncCoreEndturnSkips);
	// PRD-I3 Session E: terrain alien/endturn skips (unitsCore discipline), so a test
	// can assert exactly where the promoted terrain bucket was skipped.
	node["terrainAlienSkips"] = static_cast<Json::UInt64>(g_syncTerrainAlienSkips);
	node["terrainEndturnSkips"] = static_cast<Json::UInt64>(g_syncTerrainEndturnSkips);
	// PRD-I3 Session F: items/itemIdCtr alien/endturn skips (terrain/unitsCore discipline),
	// so a test can assert exactly where the promoted item buckets were skipped.
	node["itemsAlienSkips"] = static_cast<Json::UInt64>(g_syncItemsAlienSkips);
	node["itemsEndturnSkips"] = static_cast<Json::UInt64>(g_syncItemsEndturnSkips);
	// PRD-I3 Session F: corpse-replay-pending skips (items/itemIdCtr + saveBlob), so a test
	// can assert the sidestart straddle was a mid-flight corpse, not a persistent drift.
	node["itemsCorpsePendingSkips"] = static_cast<Json::UInt64>(g_syncItemsCorpsePendingSkips);
	node["saveBlobCorpsePendingSkips"] = static_cast<Json::UInt64>(g_syncSaveBlobCorpsePendingSkips);
	// PRD-I3 saveBlob endturn straddle: the endturn saveBlob exclusion + the sidestart
	// saveBlob compares (mirrors the hazard split above), so a test can assert saveBlob
	// rides SIDESTART only - endturn skipped, sidestart compared.
	node["saveBlobEndturnSkips"] = static_cast<Json::UInt64>(g_syncSaveBlobEndturnSkips);
	node["saveBlobSidestartCompares"] = static_cast<Json::UInt64>(g_syncSaveBlobSidestartCompares);

	Json::Value buckets(Json::objectValue);
	std::uint64_t total = 0;
	for (int i = 0; i < BATTLE_HASH_BUCKETS; ++i)
	{
		Json::Value b(Json::objectValue);
		b["alarm"] = battleHashBucketAlarms(i); // EFFECTIVE (report-only override applies)
		b["mismatchCount"] = static_cast<Json::UInt64>(g_syncBucketMismatches[i]);
		b["compares"] = static_cast<Json::UInt64>(g_syncBucketCompares[i]);
		buckets[BATTLE_HASH_NAMES[i]] = b;
		total += g_syncBucketMismatches[i];
	}
	// PRD-I2: the eighth, boundary-only bucket. Kept out of the raw `battleHashes`
	// sweep (harness `sync_buckets` still sees the seven) but reported here so the
	// harness can read its report-only counter and the cost of the last serialize.
	{
		Json::Value sb(Json::objectValue);
		sb["alarm"] = saveBlobAlarms(); // EFFECTIVE (report-only override applies)
		sb["mismatchCount"] = static_cast<Json::UInt64>(g_syncSaveBlobMismatches);
		sb["compares"] = static_cast<Json::UInt64>(g_syncSaveBlobSidestartCompares);
		buckets["saveBlob"] = sb;
		total += g_syncSaveBlobMismatches;
	}
	node["saveBlobUs"] = static_cast<Json::UInt>(g_lastSaveBlobUs);
	node["buckets"] = buckets;
	node["mismatchCount"] = static_cast<Json::UInt64>(total);

	Json::Value list(Json::arrayValue);
	for (const auto& m : g_syncMismatches)
	{
		Json::Value j(Json::objectValue);
		j["seq"] = static_cast<Json::UInt>(m.seq);
		j["boundary"] = m.boundary;
		j["kind"] = m.kind;
		j["bucket"] = m.bucket;
		list.append(j);
	}
	node["mismatches"] = list;

	// PRD-I3 SEAM-7: the exact per-unit field disagreements behind a unitsStats
	// mismatch, populated only when the opt-in field capture was armed on both machines.
	Json::Value fdiffs(Json::arrayValue);
	for (const auto& d : g_syncFieldDiffs)
	{
		Json::Value j(Json::objectValue);
		j["seq"] = static_cast<Json::UInt>(d.seq);
		j["boundary"] = d.boundary;
		j["kind"] = d.kind;
		j["unit"] = d.unitId;
		j["field"] = d.field;
		j["host"] = static_cast<Json::Int64>(d.host);
		j["peer"] = static_cast<Json::Int64>(d.peer);
		fdiffs.append(j);
	}
	node["fieldDiffs"] = fdiffs;
	node["fieldCapture"] = g_syncFieldCapture;

	out["syncCheck"] = node;
}

Json::Value desyncComputeAttribution(Game* game, const DesyncTerms& terms)
{
	// A peer told us: reuse the detector's attribution verbatim so both bundles agree.
	if (terms.attribution.isObject() && !terms.attribution.empty())
		return terms.attribution;

	Json::Value a(Json::objectValue);
	Language* lang = game ? game->getLanguage() : nullptr;

	// Prefer the sync-check's own verdict: the most recent mismatch (an ALARM one if
	// any), which names the exact seq / action kind / bucket. In classic co-op the
	// sync-check is inert (parallelTurnActive() false) and this list is empty, so the
	// P2 term fallback below runs instead.
	const SyncMismatch* lastAny = nullptr;
	const SyncMismatch* lastAlarm = nullptr;
	for (const auto& m : g_syncMismatches)
	{
		lastAny = &m;
		bool isAlarm = false;
		for (int i = 0; i < BATTLE_HASH_BUCKETS; ++i)
			if (m.bucket == BATTLE_HASH_NAMES[i]) isAlarm = battleHashBucketAlarms(i);
		if (m.bucket == "saveBlob") isAlarm = saveBlobAlarms();
		if (isAlarm) lastAlarm = &m;
	}
	const SyncMismatch* pick = lastAlarm ? lastAlarm : lastAny;
	if (pick)
	{
		a["source"] = "sync_check";
		a["seq"] = (Json::UInt)pick->seq;
		a["boundary"] = pick->boundary;
		a["kind"] = pick->kind;
		a["bucket"] = pick->bucket;
		std::string headline;
		if (lang)
			headline = lang->getString("STR_COOP_DESYNC_HEADLINE_ACTION")
				.arg(pick->bucket).arg((int)pick->seq)
				.arg(pick->kind.empty() ? std::string("?") : pick->kind);
		a["headline"] = headline;
		return a;
	}

	// Fallback: name which P2 checksum family diverged.
	std::string which;
	if (terms.peerItemId >= 0 && terms.peerItemId != terms.localItemId) which += "itemId ";
	if (terms.peerCensus >= 0 && terms.peerCensus != terms.localCensus) which += "census ";
	if (terms.peerUnits >= 0 && terms.peerUnits != terms.localUnits) which += "units ";
	if (which.empty()) which = "unknown";
	while (!which.empty() && which.back() == ' ') which.pop_back();
	a["source"] = "terms";
	a["seq"] = 0;
	a["boundary"] = false;
	a["kind"] = terms.context;
	a["bucket"] = which;
	std::string headline;
	if (lang)
		headline = lang->getString("STR_COOP_DESYNC_HEADLINE_TERM").arg(which);
	a["headline"] = headline;
	return a;
}

void desyncEmbedSyncState(Json::Value& out)
{
	Json::Value sc(Json::objectValue);
	syncCheckReport(sc);              // sc["syncCheck"] = {buckets, mismatches, ...}
	out["sync_check"] = sc["syncCheck"];

	// Ring snapshot: the last ~16 recorded seqs (compared or not), oldest first.
	Json::Value ring(Json::arrayValue);
	const size_t maxN = 16;
	const size_t start = g_syncRing.size() > maxN ? g_syncRing.size() - maxN : 0;
	for (size_t i = start; i < g_syncRing.size(); ++i)
	{
		const SyncRingEntry& e = g_syncRing[i];
		Json::Value j(Json::objectValue);
		j["seq"] = (Json::UInt)e.seq;
		j["side_seq"] = (Json::UInt)e.sideSeq;
		j["kind"] = e.kind;
		j["boundary"] = e.boundary;
		j["compared"] = e.compared;
		ring.append(j);
	}
	out["sync_ring"] = ring;
}

void resetSyncCheck()
{
	g_syncRing.clear();
	g_syncMismatches.clear();
	for (int i = 0; i < BATTLE_HASH_BUCKETS; ++i) { g_syncBucketMismatches[i] = 0; g_syncBucketCompares[i] = 0; }
	g_syncEndturnHazardSkips = 0;
	g_syncSidestartHazardCompares = 0;
	g_syncRegenAiSkips = 0;
	g_syncRegenEndturnSkips = 0;
	g_syncCoreAlienSkips = 0;
	g_syncCoreEndturnSkips = 0;
	g_syncTerrainAlienSkips = 0;
	g_syncTerrainEndturnSkips = 0;
	g_syncSaveBlobMismatches = 0;
	g_syncSaveBlobEndturnSkips = 0;
	g_syncSaveBlobSidestartCompares = 0;
	g_syncLastSeq = 0;
	g_syncLastComparedSeq = 0;
	g_syncLastBoundarySeq = 0;
	g_syncLastComparedBoundarySeq = 0;
	g_syncCompares = 0;
	g_syncStaleReports = 0;
	g_syncDropped = 0;
	g_syncKindCompares.clear();
	// PRD-I3 SEAM-7: per-episode field-diff diagnostics reset with the ring; the
	// capture TOGGLE is deliberately NOT reset here (the harness arms it once per run).
	g_syncFieldDiffs.clear();
	// PRD-I3 SEAM-3: per-episode terrain capture ring resets with the sync ring; the
	// terrain capture TOGGLE, like the SEAM-7 one, is armed once per run and kept.
	g_terrainCaptureRing.clear();
}

void attachWorldChecksum(Game* game, Json::Value& msg)
{
	if (!game || !game->getSavedGame()) return;
	SavedGame* save = game->getSavedGame();
	msg["chkFunds"] = Json::Value::Int64(save->getFunds());
	msg["chkBases"] = (int)save->getBases()->size();
	msg["chkResearch"] = (int)save->getDiscoveredResearch().size();

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

	// PRD-P2 3a: the battle terms ride along whenever a battle is live, so the
	// harness' shared_checksum hook exposes them without a second command. No-op on
	// the geoscape heartbeat, where there is no battle to stamp.
	attachBattleChecksum(game, msg);
}

bool requestResync(Game* game, const std::string& why, bool force)
{
	if (!game || !game->getCoopMod() || !game->getCoopMod()->isSharedReplica()) return false;
	if (!force && g_resyncPending) return false;

	g_resyncPending = true;
	g_lastResyncGameMin = gameMinutes(game->getSavedGame());
	++g_resyncReqN;
	Log(LOG_WARNING) << "[SHARED] requesting a world resync from the host (" << why
		<< (force ? ", forced)" : ")");

	Json::Value req;
	req["state"] = "shared_resync_request";
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
}

void verifyWorldChecksum(Game* game, const Json::Value& msg)
{
	if (!game || !game->getSavedGame()) return;
	if (!msg.isMember("chkFunds")) return; // older/non-SHARED host
	// PRD-P2 3a: the battle terms are compared on their OWN path and are deliberately
	// NOT folded into the world condition below - that condition's repair is
	// sharedResyncStream, and a mid-battle world restream tears down the live battle.
	verifyBattleChecksum(game, msg, "world checksum");
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
	int64_t myFunds = save->getFunds();
	int myBases = (int)save->getBases()->size();
	int myResearch = (int)save->getDiscoveredResearch().size();
	int mySites = (int)save->getMissionSites()->size();
	int64_t myItems, mySoldiers, myTransfers, myProductions;
	worldAggregates(save, myItems, mySoldiers, myTransfers, myProductions);
	if (hostFunds == myFunds && hostBases == myBases && hostResearch == myResearch
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
			<< ", sites host=" << hostSites << " replica=" << mySites;
	}

	const int64_t now = gameMinutes(save);
	const bool cooling = (g_lastResyncGameMin >= 0 && now >= 0
		&& now - g_lastResyncGameMin < RESYNC_COOLDOWN_MINUTES);

	if (g_resyncPending)
	{
		// A restream is already on the wire: every heartbeat until it lands still
		// mismatches, and re-asking would queue a second serialization of the whole
		// world on the host. Wait for it - but not forever: if the host dropped the
		// request (its single-slot streamer was busy) the guard expires with the
		// cooldown and the next mismatch re-asks.
		if (cooling) return;
		g_resyncPending = false;
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
	resetBattleDesyncSeen(); // PRD-P2: same "clear the diagnostics" request
	resetSyncCheck();        // PRD-I0: and the per-action detector's ring + latches
}

// ---- PRD-P4: Tier-A spawn id-manifest ----------------------------------------
// See SharedEcon.h for what a Tier-A spawn is and why the ids have to be shipped.
namespace {

struct CoopSpawnKey
{
	std::string action;
	int subject;
	bool operator<(const CoopSpawnKey& o) const
	{
		if (action != o.action) return action < o.action;
		return subject < o.subject;
	}
};

struct CoopSpawnEntry
{
	std::deque<int> ids;   // not yet consumed, in creation order
	int maxHostId = -1;    // highest id the manifest EVER held (survives popping)
};

/// Parked id lists. TRANSIENT - nothing here is ever serialised, and every entry
/// is dropped at the latest by the next turn boundary (clearSpawnManifests).
std::map<CoopSpawnKey, CoopSpawnEntry> g_spawnManifest;

/// Counter re-slave, applied AFTER a manifest has been consumed - never before.
/// Order matters: the peer's factories still mint a local id first and only then
/// adopt the host's, so bumping the counter up front would push that local mint
/// one past where the host's went and leave the counters permanently one apart.
/// Same rule SavedBattleGame's loader applies to a save's item ids. Only ever
/// moves FORWARD, so it can only close a gap, never open one.
void reslaveItemCounter(SavedBattleGame* battle, int maxHostId,
						const std::string& action, int subject)
{
	if (!battle || maxHostId < 0) return;
	int* counter = battle->getCurrentItemId();
	if (!counter || *counter >= maxHostId + 1) return;
	Log(LOG_INFO) << "[COOP] id-manifest: item-id counter re-slaved " << *counter << " -> "
				  << (maxHostId + 1) << " (" << action << " subject " << subject << ")";
	*counter = maxHostId + 1;
}

/// A frame is one OPEN record (host, appending) or guard (peer, consuming). A
/// STACK, not a single "active subject": the guards are per call by design, and a
/// nested spawn must not silently steal the outer one's ids (hole H2).
struct CoopSpawnFrame
{
	CoopSpawnKey key;
	bool consuming; // false = host record, true = peer guard
	int adopted = 0; // peer: how many host ids this scope has taken
	// PRD-P10: the peer's battle, so noteMintedItem can hand back the local id an
	// adoption just wasted (see there).
	SavedBattleGame* battle = nullptr;
};
std::vector<CoopSpawnFrame> g_spawnFrames;

/// A runaway store would be a slow leak, not a desync - but a bound makes that
/// impossible to miss instead of impossible to see.
const size_t kMaxParkedManifests = 64;

/// PRD-P10: units whose corpse replay is pushed but has not converted yet. See
/// SharedEcon.h's noteCorpseReplayPending for the double-death shape.
std::set<int> g_corpseReplayPending;

/// PRD-I3 Session F: units whose corpse this CLIENT minted with LOCAL ids (no host
/// manifest was available at mint, so path a could not adopt) and whose host ids have
/// not yet arrived on `after_unit_death`. The corpse id/counter is drifted in this
/// window (when the counter was already off), so the per-action sync-check would fire
/// items/itemIdCtr at a PLAYER-side casualty seq (window 2, complementing the
/// corpseReplayPending window 1 which is cleared just BEFORE the mint). Cleared when
/// `after_unit_death` reconciles the unit (remapCorpseIds) or at the turn boundary.
std::set<int> g_corpseRemapPending;

} // namespace

CoopSpawnRecord::CoopSpawnRecord(const char* action, int subject) : _open(false)
{
	if (!connectionTCP::getCoopStatic() || !connectionTCP::getHost()) return;

	CoopSpawnKey key{action ? action : "", subject};
	// A record OWNS its key for the duration: start from empty, so a repeat of the
	// same action on the same subject never appends onto an unflushed tail.
	g_spawnManifest[key] = CoopSpawnEntry();
	g_spawnFrames.push_back(CoopSpawnFrame{key, false, 0});
	_open = true;
}

CoopSpawnRecord::~CoopSpawnRecord()
{
	if (!_open) return;
	if (!g_spawnFrames.empty()) g_spawnFrames.pop_back();
	// The ids stay parked: flushSpawnRecord() is what ships and drops them.
}

CoopSubjectGuard::CoopSubjectGuard(SavedBattleGame* battle, const char* action, int subject)
	: _open(false), _battle(battle), _action(action ? action : ""), _subject(subject)
{
	if (!connectionTCP::getCoopStatic() || connectionTCP::getHost()) return;

	g_spawnFrames.push_back(CoopSpawnFrame{CoopSpawnKey{_action, _subject}, true, 0, battle});
	_open = true;
}

CoopSubjectGuard::~CoopSubjectGuard()
{
	if (!_open) return;
	int adopted = 0;
	if (!g_spawnFrames.empty())
	{
		adopted = g_spawnFrames.back().adopted;
		g_spawnFrames.pop_back();
	}
	if (adopted > 0)
	{
		// One line per applied manifest, mirroring remapCorpseIds - positive
		// evidence that the consume-on-create path RAN, which "the ids happened to
		// agree anyway" cannot give on its own.
		Log(LOG_INFO) << "[COOP] id-manifest: " << _action << " manifest for subject "
					  << _subject << " applied - " << adopted << " id(s) adopted on create";
	}

	CoopSpawnKey key{_action, _subject};
	auto it = g_spawnManifest.find(key);
	if (it != g_spawnManifest.end())
	{
		if (!it->second.ids.empty())
		{
			Log(LOG_INFO) << "[COOP] id-manifest: " << it->second.ids.size() << " host id(s) left over "
						  << "after replaying " << _action << " for subject " << _subject
						  << " - this machine created fewer items than the host did";
		}
		reslaveItemCounter(_battle, it->second.maxHostId, _action, _subject);
		g_spawnManifest.erase(it);
	}

	// PRD-I3 Session F window 2: a corpse this replay minted with NO host manifest in
	// hand (adopted == 0) carries LOCAL ids until `after_unit_death` remaps them - so a
	// per-action items/itemIdCtr compare in that window would false-fire on a PLAYER-side
	// casualty. Mark the unit; the after_unit_death handler clears it. (adopted > 0 means
	// path a already stamped the host's ids at mint, so there is no drift and no mark.)
	if (_action == "corpse" && adopted == 0)
	{
		g_corpseRemapPending.insert(_subject);
	}
}

void noteMintedItem(BattleItem* item)
{
	// The overwhelmingly common case, and the only one on the hot path: no Tier-A
	// spawn is in progress (and in a single-player game there never is one).
	if (g_spawnFrames.empty() || !item) return;

	CoopSpawnFrame& frame = g_spawnFrames.back();
	auto it = g_spawnManifest.find(frame.key);
	if (!frame.consuming)
	{
		if (it == g_spawnManifest.end())
		{
			it = g_spawnManifest.emplace(frame.key, CoopSpawnEntry()).first;
		}
		it->second.ids.push_back(item->getId());
		return;
	}

	// Peer: adopt the host's id for this position in the creation order. Running
	// dry is not an error worth shouting about - it is exactly what an older host
	// (no manifest at all) looks like.
	if (it == g_spawnManifest.end() || it->second.ids.empty()) return;
	const int hostId = it->second.ids.front();
	it->second.ids.pop_front();
	++frame.adopted;
	const int localId = item->getId();
	if (hostId != localId)
	{
		Log(LOG_INFO) << "[COOP] id-manifest: " << frame.key.action << " subject "
					  << frame.key.subject << " - re-stamping local item " << localId
					  << " as host item " << hostId;
	}
	item->setIdCoop(hostId);

	// PRD-P10: hand the wasted local id BACK.
	//
	// The factory minted `localId` and bumped the counter past it; adopting the
	// host's id leaves that number unused here and used nowhere on the host, so
	// keeping the counter past it puts the peer permanently one ahead. It only
	// shows when the adopted id is LOWER than the local one - i.e. when the two
	// machines created this Tier-A batch in a different ORDER, which is exactly
	// what a peer whose death replays are queued behind an animation does. The
	// counter is only rolled back when `localId` is provably the last id minted;
	// reslaveItemCounter still pushes it forward afterwards, so this can only
	// close a gap the peer opened, never hand out an id twice.
	if (hostId != localId && frame.battle)
	{
		int* counter = frame.battle->getCurrentItemId();
		if (counter && *counter == localId + 1)
		{
			*counter = localId;
		}
	}
}

void flushSpawnRecord(Json::Value& root, const char* action, int subject)
{
	CoopSpawnKey key{action ? action : "", subject};
	auto it = g_spawnManifest.find(key);
	if (it == g_spawnManifest.end()) return;
	if (!it->second.ids.empty())
	{
		Json::Value ids(Json::arrayValue);
		for (int id : it->second.ids) ids.append(id);
		root["minted_ids"] = ids;
		Log(LOG_INFO) << "[COOP] id-manifest: shipping " << it->second.ids.size() << " "
					  << key.action << " id(s) for subject " << subject;
	}
	g_spawnManifest.erase(it);
}

bool storeSpawnManifest(SavedBattleGame* battle, const char* action, int subject,
						const Json::Value& root)
{
	if (!root.isMember("minted_ids")) return false; // older host: nothing to adopt
	const Json::Value& ids = root["minted_ids"];
	if (!ids.isArray() || ids.empty()) return false;

	if (g_spawnManifest.size() > kMaxParkedManifests)
	{
		Log(LOG_ERROR) << "[COOP] id-manifest: " << g_spawnManifest.size()
					   << " manifests parked and never consumed - dropping them all";
		g_spawnManifest.clear();
	}

	CoopSpawnEntry parked;
	for (Json::ArrayIndex i = 0; i < ids.size(); ++i)
	{
		const int id = ids[i].asInt();
		parked.ids.push_back(id);
		if (id > parked.maxHostId) parked.maxHostId = id;
	}
	g_spawnManifest[CoopSpawnKey{action ? action : "", subject}] = parked;
	// NOTE: the counter is NOT re-slaved here. It is re-slaved once the manifest has
	// been APPLIED (the guard's destructor, or the end of remapCorpseIds) - see
	// reslaveItemCounter for why doing it up front is off by one.
	(void)battle;
	return true;
}

void noteCorpseReplayPending(int unitId)
{
	if (!connectionTCP::getCoopStatic() || connectionTCP::getHost()) return;
	g_corpseReplayPending.insert(unitId);
}

void clearCorpseReplayPending(int unitId)
{
	g_corpseReplayPending.erase(unitId);
}

bool corpseReplayPending(int unitId)
{
	return g_corpseReplayPending.count(unitId) != 0;
}

bool corpseReplayPendingAny()
{
	return !g_corpseReplayPending.empty();
}

void clearCorpseRemapPending(int unitId)
{
	g_corpseRemapPending.erase(unitId);
}

bool corpseRemapPendingAny()
{
	return !g_corpseRemapPending.empty();
}

int remapCorpseIds(SavedBattleGame* battle, int unitId)
{
	if (!battle) return 0;
	CoopSpawnKey key{"corpse", unitId};
	auto it = g_spawnManifest.find(key);
	if (it == g_spawnManifest.end() || it->second.ids.empty()) return 0;

	// PRD-P10: the replay is still queued, so every BT_CORPSE item this unit owns
	// right now pre-dates this death (the body item of an earlier knockout). Leave
	// the manifest parked - the CoopSubjectGuard inside the replay's
	// convertUnitToCorpse (path a) is the one that must consume it.
	if (g_corpseReplayPending.count(unitId))
	{
		Log(LOG_INFO) << "[COOP] id-manifest: corpse manifest for unit " << unitId
					  << " parked - this machine's death replay has not converted yet";
		return 0;
	}

	// _items is append-ordered, so this walk yields the corpses in the order
	// UnitDieBState created them - which is the order the host recorded them in.
	std::vector<BattleItem*> corpses;
	for (BattleItem* item : *battle->getItems())
	{
		if (!item || !item->getRules()) continue;
		if (item->getRules()->getBattleType() != BT_CORPSE) continue;
		const BattleUnit* owner = item->getUnit();
		if (owner && owner->getId() == unitId) corpses.push_back(item);
	}
	if (corpses.empty())
	{
		// Not an error: the replay has not created them yet, so the guard around
		// that creation (path a) is the one that will consume this manifest.
		return 0;
	}

	if (corpses.size() != it->second.ids.size())
	{
		Log(LOG_ERROR) << "[COOP] id-manifest: unit " << unitId << " has " << corpses.size()
					   << " corpse item(s) here but the host minted " << it->second.ids.size()
					   << " - re-stamping the common prefix only";
	}
	int n = 0, changed = 0;
	for (BattleItem* corpse : corpses)
	{
		if (it->second.ids.empty()) break;
		const int hostId = it->second.ids.front();
		it->second.ids.pop_front();
		if (hostId != corpse->getId())
		{
			Log(LOG_INFO) << "[COOP] id-manifest: corpse of unit " << unitId
						  << " re-stamped " << corpse->getId() << " -> " << hostId;
			++changed;
		}
		corpse->setIdCoop(hostId);
		++n;
	}
	// One line per applied manifest, always: "0 re-stamped" is the healthy answer
	// and is the only positive evidence that the pilot ran at all.
	Log(LOG_INFO) << "[COOP] id-manifest: corpse manifest for unit " << unitId << " applied - "
				  << n << " corpse(s), " << changed << " re-stamped";
	reslaveItemCounter(battle, it->second.maxHostId, key.action, unitId);
	g_spawnManifest.erase(it);
	return n;
}

void clearSpawnManifests()
{
	// PRD-P10: a corpse manifest whose death replay is still QUEUED on this
	// machine is not stale - it is the id list that replay is about to adopt
	// (path a). The turn boundary crosses in the middle of a death routinely (the
	// alien side's last casualty dies a frame or two before the side closes), and
	// dropping it there left the peer minting its own corpse ids off a counter
	// the host had already moved past.
	size_t kept = 0, dropped = 0;
	for (auto it = g_spawnManifest.begin(); it != g_spawnManifest.end(); )
	{
		if (it->first.action == "corpse" && g_corpseReplayPending.count(it->first.subject))
		{
			++kept;
			++it;
			continue;
		}
		it = g_spawnManifest.erase(it);
		++dropped;
	}
	if (dropped)
	{
		Log(LOG_INFO) << "[COOP] id-manifest: dropping " << dropped
					  << " manifest(s) that were never consumed";
	}
	if (kept)
	{
		Log(LOG_INFO) << "[COOP] id-manifest: keeping " << kept
					  << " manifest(s) whose death replay has not converted yet";
	}
	// Hygiene for the pending flags themselves: one with nothing parked behind it
	// can no longer be waiting for a manifest (a respawn took convertUnit instead,
	// a chain was torn down), so it would only keep exempting this unit from the
	// tile repair forever.
	for (auto it = g_corpseReplayPending.begin(); it != g_corpseReplayPending.end(); )
	{
		if (g_spawnManifest.count(CoopSpawnKey{"corpse", *it}))
		{
			++it;
		}
		else
		{
			it = g_corpseReplayPending.erase(it);
		}
	}
	// PRD-I3 Session F window 2 (safety): by a turn boundary every death's
	// `after_unit_death` has crossed (it is sent at the death's deinit, within the side),
	// so any lingering remap-pending mark is stale - clear it so items/itemIdCtr are never
	// skipped past the death that set it.
	g_corpseRemapPending.clear();
}

} // namespace SharedEcon
} // namespace OpenXcom
