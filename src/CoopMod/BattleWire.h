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
/// battle_ready) or SPEC 16 (W1-P17) M4's graceful-leave kind
/// (battle_leave), or SPEC 19 (W1-P20) M2 Branch B's guest-roster census kind
/// (battle_roster_contrib), or SPEC 17 (W1-P18) M3's per-seat animation-pacing
/// kinds (battle_speed_report/battle_speed_seats - SESSION-LEVEL, G1: never
/// bt_ev, never seq-ordered, never hashed). bt_desync (client->host) is also
/// a "bt_" kind and therefore routes to the battle lane.
inline bool isBattleKind(const std::string& state)
{
	static const std::string kPrefix = "bt_";
	if (state.compare(0, kPrefix.size(), kPrefix) == 0)
	{
		return true;
	}
	return state == "battle_offer" || state == "battle_accept" ||
		state == "battle_refuse" || state == "battle_ready" ||
		state == "battle_leave" || state == "battle_roster_contrib" ||
		state == "battle_speed_report" || state == "battle_speed_seats";
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

/// bt_desync {state, battleId, seq, bucket, expect, got, bundlePath?}
/// (SS2.3, client->host). R2-P9: sent once per battle (CoopHashCheck::
/// verify latches on the first mismatch, SS2.8 "NO partial repair") when the
/// client's post-apply hash compare disagrees with a bucket the host
/// carried in @a seq's ev/action_end. @a bundlePath is set by the caller
/// only when SharedEcon::writeDesyncBundle() succeeded (best-effort, may be
/// empty).
inline Json::Value makeDesync(uint32_t battleId, uint32_t seq, const char* bucket,
	const std::string& expect, const std::string& got)
{
	Json::Value obj(Json::objectValue);
	obj["state"] = "bt_desync";
	obj["battleId"] = battleId;
	obj["seq"] = seq;
	obj["bucket"] = bucket;
	obj["expect"] = expect;
	obj["got"] = got;
	return obj;
}

/// battle_leave {state, seat, reasonKey} (SPEC 16 W1-P17 M4). Client->host,
/// sent BEFORE the client's own teardown on a deliberate `disconnect_to_menu`
/// so the host's pause dialog can name the reason (F341: NOT a latency
/// mechanism - liveness detection alone already raises the pause dialog in
/// ~0.1s). @a reasonKey is wave-1's one value, "quit" - a deliberate leave;
/// anything else (kill/socket loss) never sends this message at all, and the
/// host's own liveness detection is what pauses the battle instead.
inline Json::Value makeLeave(int seat, const char* reasonKey)
{
	Json::Value obj(Json::objectValue);
	obj["state"] = "battle_leave";
	obj["seat"] = seat;
	obj["reasonKey"] = reasonKey;
	return obj;
}

/// battle_roster_contrib {state, seat:int, baseId:int, craftId:int,
/// craftType:string, soldiers:[string YAML]} (SPEC 19 W1-P20 M2 Branch B).
/// Client->host, battle lane, NOT seq-ordered (isSeqOrdered() above only
/// lists bt_ev/bt_action_end), NEVER hashed. @a baseId/@a craftId/@a
/// craftType name the PEER (host) base/craft the sender's guest soldiers are
/// seated on/at (Soldier::getCoopBase()/getCoopCraft()/getCoopCraftType());
/// @a soldiers is each guest's own YAML save (Soldier::save(), the same
/// form Soldier::load() consumes) - the geoscape-side data a craft-landing
/// merge needs BEFORE generation (F359/F360/F365). Sent from
/// connectionTCP::sendGuestRosterContrib() (the sendGuestCensus() pattern -
/// computed every tick, sent only when the serialized set for this
/// destination differs from the last sent, plus once on connect). Consumed,
/// host-inbound only, at the craft-landing entry
/// (CoopBattleSetup.h::coopMergeGuestContributions(), called from
/// ConfirmLandingState::btnYesClick before generation); the per-seat store is
/// cleared by resetBattleAuthority() (connectionTCP.cpp).
/// W2-H19 (F6860): the battle-end reset (coopResetBattleScope) keeps a roster
/// that arrived after the battle ended (it is for the next landing); after
/// every battle-scope reset the sender resends its whole roster once; an empty
/// @a soldiers list drops a destination whose guest left the craft.
/// W2-H19b (F6989): the host keeps one entry per seat AND destination (craftId +
/// craftType); a landing merges only the landing craft's entry.
inline Json::Value makeRosterContrib(int seat, int baseId, int craftId, const char* craftType,
	const std::vector<std::string>& soldiers)
{
	Json::Value obj(Json::objectValue);
	obj["state"] = "battle_roster_contrib";
	obj["seat"] = seat;
	obj["baseId"] = baseId;
	obj["craftId"] = craftId;
	obj["craftType"] = craftType;
	Json::Value arr(Json::arrayValue);
	for (const auto& yaml : soldiers)
	{
		arr.append(yaml);
	}
	obj["soldiers"] = arr;
	return obj;
}

/// battle_speed_report {state, battleId:uint, seat:int, xcom:int, alien:int,
/// fire:int} (SPEC 17 W1-P18 M3). Client->host, battle lane, NOT seq-ordered,
/// NEVER hashed (G1: session-level only, nothing per-event). Sent from
/// CoopSpeed::onLocalChanged() whenever this CLIENT's own
/// battleXcomSpeed/battleAlienSpeed/battleFireSpeed dials change (or have
/// never been reported yet this battle). @a seat is the sender's own seat.
inline Json::Value makeSpeedReport(uint32_t battleId, int seat, int xcom, int alien, int fire)
{
	Json::Value obj(Json::objectValue);
	obj["state"] = "battle_speed_report";
	obj["battleId"] = battleId;
	obj["seat"] = seat;
	obj["xcom"] = xcom;
	obj["alien"] = alien;
	obj["fire"] = fire;
	return obj;
}

/// battle_speed_seats {state, battleId:uint, seq:uint,
/// seats:[{seat:int,xcom:int,alien:int,fire:int}...]} (SPEC 17 W1-P18 M3).
/// Host->client(s), battle lane, NOT seq-ordered, NEVER hashed. The FULL
/// table of every seat CoopSpeed considers connected+valid right now
/// (including the reporting client's own entry mirrored straight back).
/// Sent from CoopSpeed::tableChanged() (HOST only) whenever the table
/// changes; @a seq lets a client ignore a stale/out-of-order copy.
inline Json::Value makeSpeedSeats(uint32_t battleId, uint32_t seq, const Json::Value& seats)
{
	Json::Value obj(Json::objectValue);
	obj["state"] = "battle_speed_seats";
	obj["battleId"] = battleId;
	obj["seq"] = seq;
	obj["seats"] = seats;
	return obj;
}

/// bt_debrief_result {state, battleId:uint, debrief:{titleKey:string,
/// recoveryKey:string, stats:[{item, qty, score, recovery}], soldiers:[{name,
/// stats:[12 ints]}], recovered:[{item, qty}]}} (W2-P7 S-B1, plan section 4
/// `debrief_result`, Q1 (a)). Host->client, battle lane, NOT seq-ordered
/// (isSeqOrdered() above), NEVER hashed, never an ev. The display content the
/// host's own vanilla debrief computed: `stats` = every DebriefingStat with a
/// non-zero qty in order (`item` = the STR id), `soldiers` = the stat gains in
/// UnitStats member order (tu, stamina, health, bravery, reactions, firing,
/// throwing, strength, psiStrength, psiSkill, melee, mana), `recovered` = item
/// type ids in the mod's item-list order; `titleKey` / `recoveryKey` are the keys
/// the host's prepareDebriefing used; each machine renders them (AUD-A12). Total and rating are derived on the client.
inline Json::Value makeDebriefResult(uint32_t battleId, const Json::Value& debrief)
{
	Json::Value obj(Json::objectValue);
	obj["state"] = "bt_debrief_result";
	obj["battleId"] = battleId;
	obj["debrief"] = debrief;
	return obj;
}

/// bt_fatal_vote_answer {state, battleId:uint, voteId:uint, seat:int, yes:bool} (W2-P7 S-V, the design's section
/// 2.3; AMENDMENT P7-5 section 4.3). Client->host, battle lane, NOT seq-ordered (isSeqOrdered() above), never hashed,
/// never an ev: one voter's answer to the fatal-wounds question (OK = yes; CANCEL, Esc, the abort key = no). The host
/// takes it only for this battle's open vote from a voter seat still deciding; anything else is counted and dropped.
inline Json::Value makeFatalVoteAnswer(uint32_t battleId, uint32_t voteId, int seat, bool yes)
{
	Json::Value obj(Json::objectValue);
	obj["state"] = "bt_fatal_vote_answer";
	obj["battleId"] = battleId;
	obj["voteId"] = voteId;
	obj["seat"] = seat;
	obj["yes"] = yes;
	return obj;
}

} // namespace CoopWire

} // namespace OpenXcom
