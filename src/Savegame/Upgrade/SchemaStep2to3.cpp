/*
 * Schema 2 -> 3: replace SEPARATE's embedded per-player worlds with one
 * host-authoritative world.  Every real base is copied into the host bases
 * sequence and carries its unique locked roster name in ownerplayername.
 */
#include "SaveUpgradeTypes.h"

#include <algorithm>
#include <functional>
#include <map>
#include <set>
#include <string>
#include <utility>
#include <vector>

namespace OpenXcom
{
namespace SaveUpgrade
{
namespace
{

using yamlutil::getInt;
using yamlutil::getStr;
using yamlutil::hasKey;
using yamlutil::removeKey;
using yamlutil::setInt;

int countBases(ryml::ConstNodeRef body)
{
	ryml::ConstNodeRef bases = body.find_child("bases");
	return (!bases.invalid() && bases.is_seq()) ? static_cast<int>(bases.num_children()) : 0;
}

bool hasFunds(ryml::ConstNodeRef body)
{
	ryml::ConstNodeRef funds = body.find_child("funds");
	return !funds.invalid() && funds.is_seq() && funds.num_children() != 0;
}

void copyScalarSequence(ryml::NodeRef destinationMap, ryml::csubstr destinationKey,
	ryml::NodeRef sourceSequence)
{
	if (sourceSequence.invalid() || !sourceSequence.is_seq() || sourceSequence.num_children() == 0)
		return;
	ryml::NodeRef destination = yamlutil::mapChild(destinationMap, destinationKey);
	destination |= ryml::SEQ;
	for (ryml::NodeRef value : sourceSequence.children())
		destination.append_child().set_val(
			destination.tree()->to_arena(value.val()));
}

void appendPlayerFunds(ryml::NodeRef players, const std::string& name, ryml::NodeRef sourceBody)
{
	ryml::NodeRef player = players.append_child();
	player |= ryml::MAP;
	yamlutil::setStr(player, "name", name);
	// Mod campaigns may use the difficulty selector as the player's faction.
	// Schema 2 kept that selection in each player's independent world.
	yamlutil::setStr(player, "faction", "difficulty:"
		+ std::to_string(getInt(sourceBody, "difficulty", 0)));

	// Preserve the complete history, not merely the current balance. SavedGame
	// uses the last entry as current funds and the preceding entries in graphs.
	ryml::NodeRef sourceFunds = sourceBody.find_child("funds");
	if (!sourceFunds.invalid())
	{
		const size_t after = player.num_children() ? player.last_child().id() : ryml::NONE;
		player.tree()->duplicate(sourceFunds.tree(), sourceFunds.id(), player.id(), after);
	}

	// Old Separate worlds also held their own discovery lists. They provide both
	// the private completed-research state and the faction snapshot used when
	// deciding whether a scripted mission is faction-specific.
	ryml::NodeRef discovered = sourceBody.find_child("discovered");
	copyScalarSequence(player, "completedResearch", discovered);
	copyScalarSequence(player, "factionResearch", discovered);
	ryml::NodeRef pediaStatus = sourceBody.find_child("ufopediaRuleStatus");
	if (!pediaStatus.invalid() && pediaStatus.is_map())
	{
		const size_t pediaAfter = player.num_children()
			? player.last_child().id() : ryml::NONE;
		player.tree()->duplicate(
			pediaStatus.tree(), pediaStatus.id(), player.id(), pediaAfter);
	}
}

void tagBaseTree(ryml::NodeRef base, const std::string& ownerName, int ownerSeat)
{
	yamlutil::setStr(base, "ownerplayername", ownerName);
	// Soldiers remain physically contained by their owned base.  Explicitly
	// stamp them too so battle ownership agrees with strategic ownership.
	ryml::NodeRef soldiers = base.find_child("soldiers");
	if (!soldiers.invalid() && soldiers.is_seq())
		for (ryml::NodeRef soldier : soldiers.children())
			setInt(soldier, "ownerplayerid", ownerSeat);
}

using CraftKey = std::pair<std::string, long long>;

/// Craft (type, id) pairs of one base, including crafts travelling in transfers.
void forEachCraft(ryml::NodeRef base, const std::function<void(ryml::NodeRef)>& fn)
{
	ryml::NodeRef crafts = base.find_child("crafts");
	if (!crafts.invalid() && crafts.is_seq())
		for (ryml::NodeRef craft : crafts.children())
			fn(craft);
	ryml::NodeRef transfers = base.find_child("transfers");
	if (!transfers.invalid() && transfers.is_seq())
		for (ryml::NodeRef transfer : transfers.children())
		{
			ryml::NodeRef craft = transfer.find_child("craft");
			if (!craft.invalid() && craft.is_map())
				fn(craft);
		}
}

/// An imported world's crafts may fly toward that world's UFOs, waypoints,
/// sites or crafts. Those ids name other objects (or nothing) in the host
/// world, so the craft returns to its own base instead of re-binding to a
/// wrong target (Craft::load resolves STR_BASE to returnToBase()).
int sendImportedCraftsHome(ryml::NodeRef base)
{
	int sent = 0;
	forEachCraft(base, [&](ryml::NodeRef craft)
	{
		removeKey(craft, "coopDestUfoId");
		removeKey(craft, "coopDestMissionId");
		ryml::NodeRef dest = craft.find_child("dest");
		if (dest.invalid() || !dest.is_map() || getStr(dest, "type") == "STR_BASE")
			return;
		yamlutil::setStr(dest, "type", "STR_BASE");
		++sent;
	});
	return sent;
}

/// Give an imported craft a fresh id when the host world already uses its
/// (type, id), and re-point the base's crew at it.
int renumberImportedCrafts(ryml::NodeRef base, std::set<CraftKey>& claimed,
	std::map<std::string, long long>& maxId)
{
	int changed = 0;
	ryml::NodeRef soldiers = base.find_child("soldiers");
	forEachCraft(base, [&](ryml::NodeRef craft)
	{
		const std::string type = getStr(craft, "type");
		const long long id = getInt(craft, "id", 0);
		if (claimed.insert(CraftKey(type, id)).second)
			return;
		const long long newId = ++maxId[type];
		claimed.insert(CraftKey(type, newId));
		setInt(craft, "id", newId);
		if (!soldiers.invalid() && soldiers.is_seq())
			for (ryml::NodeRef soldier : soldiers.children())
			{
				ryml::NodeRef ref = soldier.find_child("craft");
				if (!ref.invalid() && ref.is_map() && getStr(ref, "type") == type
					&& getInt(ref, "id", -1) == id)
					setInt(ref, "id", newId);
			}
		++changed;
	});
	return changed;
}

/// Schema 2 kept a soldier stationed at the other player's base in its
/// owner's roster, tagged with that base's coopbaseid. One world holds the
/// soldier where it physically is; ownerplayerid keeps it its owner's.
int relocateStationedSoldiers(ryml::NodeRef hostBases)
{
	std::map<long long, ryml::id_type> baseByCoopId;
	for (ryml::NodeRef base : hostBases.children())
	{
		const long long coopId = getInt(base, "coopbaseid", 0);
		if (coopId != 0)
			baseByCoopId[coopId] = base.id();
	}
	ryml::Tree* tree = hostBases.tree();
	int moved = 0;
	for (ryml::NodeRef base : hostBases.children())
	{
		ryml::NodeRef soldiers = base.find_child("soldiers");
		if (soldiers.invalid() || !soldiers.is_seq())
			continue;
		const long long ownId = getInt(base, "coopbaseid", 0);
		std::vector<std::pair<ryml::id_type, ryml::id_type>> toMove;
		for (ryml::NodeRef soldier : soldiers.children())
		{
			const long long station = getInt(soldier, "coopbase", -1);
			if (station == -1 || station == ownId)
				continue;
			auto target = baseByCoopId.find(station);
			if (target != baseByCoopId.end())
				toMove.push_back(std::make_pair(soldier.id(), target->second));
		}
		for (const auto& move : toMove)
		{
			ryml::NodeRef soldier = tree->ref(move.first);
			ryml::NodeRef targetSoldiers = yamlutil::mapChild(tree->ref(move.second), "soldiers");
			targetSoldiers |= ryml::SEQ;
			setInt(soldier, "coopbase", -1);
			// A guest never sits on a craft of the base it was listed under.
			removeKey(soldier, "craft");
			tree->move(move.first, targetSoldiers.id(),
				targetSoldiers.num_children() ? targetSoldiers.last_child().id() : ryml::NONE);
			++moved;
		}
	}
	return moved;
}

bool isPvp(const SaveSet& set)
{
	const long long gamemode = getInt(set.host.body(), "coop_gamemode", set.gamemode);
	return gamemode == 2 || gamemode == 3;
}

int rosterSeat(const SaveSet& set, const ClientWorld& client, size_t fallback)
{
	for (size_t i = 0; i < set.roster.size(); ++i)
		if (!client.name.empty() && set.roster[i] == client.name)
			return static_cast<int>(i);
	return static_cast<int>(fallback);
}

class Step_2_to_3 : public SchemaStep
{
public:
	int fromSchema() const override { return 2; }
	int toSchema() const override { return 3; }

	std::vector<InputRequest> requiredInputs(const SaveSet&) const override
	{
		return {};
	}

	void validate(const SaveSet& set, const UpgradeInputs&, PreflightResult& out) const override
	{
		if (!set.host.valid())
		{
			out.errors.push_back("The host save is not a valid two-document YAML stream.");
			return;
		}
		const int campaignType = static_cast<int>(getInt(set.host.header(), "coopCampaignType", 0));
		if (campaignType == 1)
			return; // SHARED already is one world; only its schema stamp changes.
		if (isPvp(set))
			return; // PvP keeps one world per player; only the stamp changes.
		std::set<std::string> playerNames;
		ryml::ConstNodeRef roster = set.host.header().find_child("coopPlayers");
		if (!roster.invalid() && roster.is_seq())
		{
			for (ryml::ConstNodeRef player : roster.children())
			{
				std::string name = player.has_val() ? std::string(player.val().str, player.val().len) : std::string();
				if (name.empty())
					out.errors.push_back("Every player needs a non-empty name for base ownership.");
				else if (!playerNames.insert(name).second)
					out.errors.push_back("Player names must be unique for base ownership: " + name);
			}
		}

		int total = countBases(set.host.body());
		for (const ClientWorld& client : set.clients)
			total += countBases(client.world.body());
		if (total == 0)
			out.errors.push_back("The separate campaign contains no bases.");
		if (total > 8)
			out.warnings.push_back("The separate campaign contains " + std::to_string(total)
				+ " bases. They will all be preserved, but no new base can be built unless the total falls below 8.");
		if (!hasFunds(set.host.body()))
			out.errors.push_back("The host world has no funds history; refusing a lossy merge.");
		for (const ClientWorld& client : set.clients)
			if (!hasFunds(client.world.body()))
				out.errors.push_back("The player world for " + client.name
					+ " has no funds history; refusing a lossy merge.");

		// A missing blob means part of the old separate campaign is unavailable.
		// Refuse instead of silently producing a save which loses that player.
		const size_t expectedClients = (!roster.invalid() && roster.is_seq() && roster.num_children() > 0)
			? roster.num_children() - 1 : 0;
		if (set.clients.size() < expectedClients)
			out.errors.push_back("One or more player worlds are missing from coopClientSaves; refusing a lossy merge.");
	}

	void apply(SaveSet& set, const UpgradeInputs&) const override
	{
		ryml::NodeRef header = set.host.header();
		setInt(header, "saveSchema", 3);
		if (getInt(header, "coopCampaignType", 0) == 1)
		{
			set.report.push_back("Schema 3: SHARED campaign already uses one authoritative world.");
			return;
		}
		if (isPvp(set))
		{
			// PvP keeps main's two worlds: the client world stays embedded.
			for (ClientWorld& client : set.clients)
				setInt(client.world.header(), "saveSchema", 3);
			set.schema = 3;
			set.report.push_back("Schema 3: PvP campaign keeps one world per player.");
			return;
		}
		// Some real intermediate embed saves predate the explicit campaign-type
		// header even though their coopClientSaves sequence unambiguously identifies
		// Separate. Stamp the current format instead of relying on a missing-key
		// default that postflight and future loaders cannot distinguish.
		setInt(header, "coopCampaignType", 0);

		// Read the roster directly when this run began at schema 2.  A chained
		// 1->2 run also populated SaveSet::roster in the preceding step.
		if (set.roster.empty())
		{
			ryml::ConstNodeRef roster = header.find_child("coopPlayers");
			if (!roster.invalid() && roster.is_seq())
				for (ryml::ConstNodeRef p : roster.children())
					set.roster.push_back(p.has_val() ? std::string(p.val().str, p.val().len) : std::string());
		}

		ryml::NodeRef hostBody = set.host.body();
		ryml::NodeRef hostBases = hostBody.find_child("bases");
		if (hostBases.invalid())
		{
			hostBases = yamlutil::mapChild(hostBody, "bases");
			hostBases |= ryml::SEQ;
		}
		const std::string hostName = set.roster.empty() ? std::string() : set.roster[0];
		for (ryml::NodeRef base : hostBases.children())
			tagBaseTree(base, hostName, 0);

		// Every craft id already used by any world, so a renumbered import never
		// collides with a craft imported later.
		std::set<CraftKey> claimedCrafts;
		std::map<std::string, long long> maxCraftId;
		auto noteMax = [&](ryml::NodeRef craft)
		{
			long long& top = maxCraftId[getStr(craft, "type")];
			top = std::max(top, getInt(craft, "id", 0));
		};
		for (ryml::NodeRef base : hostBases.children())
			forEachCraft(base, [&](ryml::NodeRef craft)
			{
				noteMax(craft);
				claimedCrafts.insert(CraftKey(getStr(craft, "type"), getInt(craft, "id", 0)));
			});
		for (ClientWorld& client : set.clients)
		{
			ryml::NodeRef bases = client.world.body().find_child("bases");
			if (!bases.invalid() && bases.is_seq())
				for (ryml::NodeRef base : bases.children())
					forEachCraft(base, noteMax);
		}
		int craftsSentHome = 0;
		int craftsRenumbered = 0;
		int deadImported = 0;

		int imported = 0;
		for (size_t i = 0; i < set.clients.size(); ++i)
		{
			ClientWorld& client = set.clients[i];
			const int owner = rosterSeat(set, client, i + 1);
			const std::string ownerName = owner >= 0 && static_cast<size_t>(owner) < set.roster.size()
				? set.roster[owner] : client.name;
			ryml::NodeRef clientBases = client.world.body().find_child("bases");
			if (clientBases.invalid() || !clientBases.is_seq())
				continue;
			for (ryml::NodeRef sourceBase : clientBases.children())
			{
				// Cross-tree duplicate copies the complete base subtree: facilities,
				// soldiers, crafts, stores, projects, productions and transfers.
				const size_t after = hostBases.num_children() ? hostBases.last_child().id() : ryml::NONE;
				size_t id = hostBases.tree()->duplicate(sourceBase.tree(), sourceBase.id(), hostBases.id(), after);
				ryml::NodeRef importedBase = hostBases.tree()->ref(id);
				tagBaseTree(importedBase, ownerName, owner);
				craftsSentHome += sendImportedCraftsHome(importedBase);
				craftsRenumbered += renumberImportedCrafts(importedBase, claimedCrafts, maxCraftId);
				++imported;
			}

			// The player's memorial: its dead soldiers stay its own.
			ryml::NodeRef clientDead = client.world.body().find_child("deadSoldiers");
			if (!clientDead.invalid() && clientDead.is_seq() && clientDead.num_children() != 0)
			{
				ryml::NodeRef hostDead = yamlutil::mapChild(hostBody, "deadSoldiers");
				hostDead |= ryml::SEQ;
				for (ryml::NodeRef dead : clientDead.children())
				{
					const size_t deadAfter = hostDead.num_children() ? hostDead.last_child().id() : ryml::NONE;
					size_t deadId = hostDead.tree()->duplicate(dead.tree(), dead.id(), hostDead.id(), deadAfter);
					setInt(hostDead.tree()->ref(deadId), "ownerplayerid", owner);
					++deadImported;
				}
			}

			// Id counters: a new object must never reuse an id the imported
			// world already handed out.
			ryml::NodeRef clientIds = client.world.body().find_child("ids");
			if (!clientIds.invalid() && clientIds.is_map())
			{
				ryml::NodeRef hostIds = yamlutil::mapChild(hostBody, "ids");
				hostIds |= ryml::MAP;
				for (ryml::NodeRef counter : clientIds.children())
				{
					if (!counter.has_key())
						continue;
					const std::string key(counter.key().str, counter.key().len);
					const long long value = getInt(clientIds, ryml::to_csubstr(key), 0);
					if (value > getInt(hostIds, ryml::to_csubstr(key), 0))
						setInt(hostIds, hostIds.tree()->to_arena(ryml::to_csubstr(key)), value);
				}
			}
		}

		const int soldiersRelocated = relocateStationedSoldiers(hostBases);
		{
			ryml::NodeRef hostIds = yamlutil::mapChild(hostBody, "ids");
			hostIds |= ryml::MAP;
			for (const auto& top : maxCraftId)
			{
				if (top.first.empty())
					continue;
				if (getInt(hostIds, ryml::to_csubstr(top.first), 0) <= top.second)
					setInt(hostIds, hostIds.tree()->to_arena(ryml::to_csubstr(top.first)), top.second + 1);
			}
		}

		// Schema 2 stored a complete SavedGame per player. Schema 3 stores one
		// strategic world, so retain each world's funds under its named player
		// profile before the embedded worlds are discarded. Without this, the
		// loader initializes every profile from the host world's legacy funds.
		removeKey(hostBody, "separateCampaign");
		ryml::NodeRef campaign = yamlutil::mapChild(hostBody, "separateCampaign");
		campaign |= ryml::MAP;
		setInt(campaign, "version", 3);
		ryml::NodeRef players = yamlutil::mapChild(campaign, "players");
		players |= ryml::SEQ;
		appendPlayerFunds(players, hostName, hostBody);
		for (size_t i = 0; i < set.clients.size(); ++i)
		{
			ClientWorld& client = set.clients[i];
			const int owner = rosterSeat(set, client, i + 1);
			const std::string ownerName = owner >= 0 && static_cast<size_t>(owner) < set.roster.size()
				? set.roster[owner] : client.name;
			appendPlayerFunds(players, ownerName, client.world.body());
		}

		removeKey(hostBody, "coopClientSaves");
		setInt(hostBody, "coop_save_owner_player_id", 0);
		set.clients.clear(); // emitter must never recreate schema-2 blobs
		set.schema = 3;
		set.report.push_back("Unified SEPARATE campaign into the host save; imported "
			+ std::to_string(imported) + " client base(s).");
		set.report.push_back("All bases now carry unique ownerplayername values; client-world blobs removed.");
		set.report.push_back("Preserved each player's faction and independent funds history in the unified save.");
		if (craftsSentHome)
			set.report.push_back(std::to_string(craftsSentHome)
				+ " imported craft(s) were flying to a target of their old world and now return to base.");
		if (craftsRenumbered)
			set.report.push_back("Renumbered " + std::to_string(craftsRenumbered)
				+ " imported craft(s) whose id the host world already used.");
		if (soldiersRelocated)
			set.report.push_back("Moved " + std::to_string(soldiersRelocated)
				+ " soldier(s) stationed at the other player's base into that base.");
		if (deadImported)
			set.report.push_back("Kept " + std::to_string(deadImported)
				+ " fallen soldier(s) from the other player's memorial.");
		if (hostBases.num_children() > 8)
			set.report.push_back("Grandfathered over-cap campaign: all "
				+ std::to_string(hostBases.num_children())
				+ " bases were preserved; construction remains locked while the total is 8 or more.");
	}
};

} // namespace

const SchemaStep* step_2_to_3()
{
	static const Step_2_to_3 instance;
	return &instance;
}

} // namespace SaveUpgrade
} // namespace OpenXcom
