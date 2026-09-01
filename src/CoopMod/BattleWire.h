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

#include <json/json.h>

namespace OpenXcom
{

/**
 * R2-P1 (rewrite spike, SPIKE-RUNBOOK.md SS2.1-SS2.3): the battle wire
 * envelope layer. Builders/parsers for the FROZEN battle-lane message
 * schemas, as inline functions over jsoncpp Json::Value - no consumers yet,
 * this is only the envelope layer + the routing predicate. Field names and
 * discriminator strings match SS2 EXACTLY; do not add/rename/drop fields
 * here without an SS2 update.
 *
 * Transport: existing framed reliable lane (appendFramed / g_txQ), same as
 * every other coop wire message - see connectionTCP.cpp. Battle kinds are
 * routed out of the legacy dispatch by isBattleKind() before the legacy
 * allowlist/hold-deque logic and the R1-P3 quarantine catch-all can see
 * them (RB-D per the routing rule in SS2.1).
 */
namespace CoopWire
{

/// SS2.1 discriminator: state starts with "bt_", or is one of the
/// battle-handshake kinds (battle_offer/battle_accept/battle_refuse/
/// battle_ready). bt_desync (client->host) is also a "bt_" kind and
/// therefore routes to the battle lane.
inline bool isBattleKind(const std::string& state)
{
	static const std::string kPrefix = "bt_";
	if (state.compare(0, kPrefix.size(), kPrefix) == 0)
	{
		return true;
	}
	return state == "battle_offer" || state == "battle_accept" ||
		state == "battle_refuse" || state == "battle_ready";
}

/// SS2.1: bt_ev and bt_action_end are the seq-ordered apply-queue kinds;
/// everything else on the battle lane is handled directly by the lane
/// dispatcher (still on the pump thread, never the socket thread).
inline bool isSeqOrdered(const std::string& state)
{
	return state == "bt_ev" || state == "bt_action_end";
}

/// bt_intent {state, iseq, seat, actorId, kind, ...concrete-plan fields}
/// (SS2.3). The caller adds the concrete-plan fields for @a kind (e.g.
/// turn/kneel, SS2.3) after this returns.
inline Json::Value makeIntent(uint32_t iseq, int seat, int actorId, const char* kind)
{
	Json::Value obj(Json::objectValue);
	obj["state"] = "bt_intent";
	obj["iseq"] = iseq;
	obj["seat"] = seat;
	obj["actorId"] = actorId;
	obj["kind"] = kind;
	return obj;
}

/// bt_ack {state, iseq, actionId} (SS2.3).
inline Json::Value makeAck(uint32_t iseq, uint32_t actionId)
{
	Json::Value obj(Json::objectValue);
	obj["state"] = "bt_ack";
	obj["iseq"] = iseq;
	obj["actionId"] = actionId;
	return obj;
}

/// bt_deny {state, iseq, reason} (SS2.3). @a reason is one of the machine
/// enum strings in SS2.2 (busy | path_changed | cost_changed |
/// target_moved | target_dead | weapon_missing | not_your_unit |
/// turn_over) - the wire never carries STR_ keys.
inline Json::Value makeDeny(uint32_t iseq, const char* reason)
{
	Json::Value obj(Json::objectValue);
	obj["state"] = "bt_deny";
	obj["iseq"] = iseq;
	obj["reason"] = reason;
	return obj;
}

/// bt_ev {state, seq, actionId, kind, payload:{...}, h?} (SS2.3). Returns
/// with an EMPTY payload object already present; the caller fills payload
/// (and, per RB-D14, the h:{unitsStats} bucket for the spike's turn/kneel
/// evs) before sending.
inline Json::Value makeEv(uint32_t seq, uint32_t actionId, const char* kind)
{
	Json::Value obj(Json::objectValue);
	obj["state"] = "bt_ev";
	obj["seq"] = seq;
	obj["actionId"] = actionId;
	obj["kind"] = kind;
	obj["payload"] = Json::Value(Json::objectValue);
	return obj;
}

/// bt_action_end {state, seq, actionId, final:{...}, halted?:bool,
/// reason?:string, h} (SS2.3). Only {state, seq, actionId} are set here;
/// the caller fills "final" (and h, halted, reason as applicable).
inline Json::Value makeActionEnd(uint32_t seq, uint32_t actionId)
{
	Json::Value obj(Json::objectValue);
	obj["state"] = "bt_action_end";
	obj["seq"] = seq;
	obj["actionId"] = actionId;
	return obj;
}

} // namespace CoopWire

} // namespace OpenXcom
