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

#include <iostream>
#include <fstream>
#include <thread>
#include <vector>
#include <array>
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <map>
#include <string>
#include <set>
#include <unordered_map>
#include <unordered_set>
#include <utility>

#include <filesystem>
#include <cctype> // std::isdigit
#include <mutex>

#include <deque>

#include <json/json.h>

#include <SDL_net.h>

#include "ServerList.h"
#include "LobbyMenu.h"

#include "CoopState.h"
#include "Profile.h"
#include "ChatMenu.h"

#include "../Engine/Options.h"

#include "../Savegame/Ufo.h"
#include "../Mod/RuleInventory.h"

#include "CrashHandler.h" // coop


#include <algorithm> // clamp, minmax
#include <cmath>     // round
#include <optional>

#ifdef _WIN32
#include <windows.h>
#endif

inline void DebugLog(const std::string& msg)
{
#ifdef _WIN32
	OutputDebugStringA(msg.c_str());
#else
	std::fprintf(stderr, "%s\n", msg.c_str());
#endif

	if (OpenXcom::Options::logInfoToFile && OpenXcom::Options::debugMode)
	{
		CrashHandler::log(msg);
	}

}

inline void DebugLog(const char* msg)
{
	DebugLog(std::string(msg));
}

// Bounded ring buffer of std::string slots. NOTE: despite the name, this is NOT
// single-producer/single-consumer in this codebase. g_txQ/g_rxQ each have 3+
// producers and 2+ consumers (main thread, network thread, loopData thread, UDP
// thread, plus clearNetworkSessionQueues). Concurrent buf[] std::string moves on
// the same slot double-free the heap (the crash mis-symbolized as SDL_FreeRW). So
// every operation is serialized by an internal mutex that covers the buf[] move,
// not just the cursor. The name is kept to avoid churn at ~40 call sites.
template <size_t N>
struct SPSCQueue
{
	std::array<std::string, N> buf{};
	size_t head{0}; // producer writes (guarded by m)
	size_t tail{0}; // consumer reads  (guarded by m)
	mutable std::mutex m;

	bool push(std::string&& s)
	{
		std::lock_guard<std::mutex> lk(m);
		size_t n = (head + 1) % N;
		if (n == tail)
			return false; // full
		buf[head] = std::move(s);
		head = n;
		return true;
	}

	bool pop(std::string& out)
	{
		std::lock_guard<std::mutex> lk(m);
		if (tail == head)
			return false; // empty
		out = std::move(buf[tail]);
		tail = (tail + 1) % N;
		return true;
	}

	bool empty() const
	{
		std::lock_guard<std::mutex> lk(m);
		return tail == head;
	}

	// coop (option 3B): current occupancy - for the live drain gauge.
	size_t size() const
	{
		std::lock_guard<std::mutex> lk(m);
		return (head + N - tail) % N;
	}

	bool full() const
	{
		std::lock_guard<std::mutex> lk(m);
		return ((head + 1) % N) == tail;
	}
};

namespace OpenXcom
{

// Shared network queues used by both connectionTCP and connectionUDP.
// Definitions must exist exactly once in a .cpp file, normally connectionTCP.cpp:
extern SPSCQueue<1024> g_txQ;
extern SPSCQueue<1024> g_rxQ;
extern int tcp_port;

// Count of packets dropped because the TX queue was full (test harness reads
// this via the coop_stats command to detect the "TX queue full" backlog bug).
extern std::atomic<uint64_t> g_txDropCount;

// PRD-P0 (harness introspection, test-only): receive-gate readout.
// updateCoopTask() parks every packet this machine is not yet allowed to
// consume in a file-scope hold deque and rotates the unconsumed ones to the
// back of it, so a test that sees a peer "not react" cannot otherwise tell a
// dropped packet from one still waiting on the local task to finish. Free
// functions/counters (not members) because the deque itself is file-scope in
// connectionTCP.cpp - same shape as g_txDropCount above, and like it both
// counters are process-monotonic (never reset).
bool rxPassDeferred();             // PRD-P2: this dispatch overtook a deferred packet
size_t rxHoldSize();               // current hold-queue depth
size_t rxParkSize();               // PRD-P9 R7: packets parked, not rotated
size_t snapshotPendingCount();     // option 3B: dirty conflation slots (live drain gauge)
extern std::atomic<uint32_t> g_rxRotateCount;   // PRD-P11: gate holds (nothing rotates now)
extern std::atomic<uint32_t> g_rxHoldMaxSeen;   // hold-queue high-water mark
// coop (PRD-P11): the in-order pump. The queue is consumed IN PLACE and a packet
// the gate refuses keeps its position, so a unit's packets can never be applied
// out of the order they were sent.
extern std::atomic<uint32_t> g_rxSkipBlocked;   // held back: an earlier packet names the same unit
extern std::atomic<uint32_t> g_rxLegacyPasses;  // liveness-floor engagements (expected 0)
extern std::atomic<uint32_t> g_rxSeqDeferred;   // PRD-I1: outcome packet held for its own chain's opener
extern std::atomic<uint32_t> g_barrierBlocks;   // PHASE D.1: action_end held until its chain's stamped packets applied
// coop (LIVENESS FLOOR ordering-preserving drain): times the stage-2 hard-floor escape
// hatch reverted the parallel replay client to the legacy full-disable (the ordered drain
// could not make progress). Process-monotonic; 0 across a run means the ordering-preserving
// drain carried the whole load and the backstop never fired.
extern std::atomic<uint32_t> g_rxHardFloorPasses;
// coop (wire-order Increment 7, SHAPE A diagnostic): regen-carry elements the HOST
// emitted on action_end markers, and elements the CLIENT applied at first-sight.
extern std::atomic<uint32_t> g_regenEmitted;
extern std::atomic<uint32_t> g_regenApplied;
// coop (three-class RCA DIAGNOSTIC): capture-gated tagged write log; lever-off inert.
extern std::atomic<bool> g_diagCapture;
extern std::vector<std::string> g_diagTrace;
extern std::mutex g_diagTraceMutex;
void coopDiagS(std::string s);
void coopDiagUnit(const char* tag, int unitId, long v);
// coop (option 3): the wire-order master lever (defined connectionTCP.cpp:639), exposed so
// SharedEcon.cpp's syncCheckCompare/verifyBattleChecksum can gate the boundary persistence
// alarm on it (lever-off = byte-identical). Standard g_ atomic extern pattern.
extern std::atomic<bool> g_wireOrderState;
// TEST-ONLY levers (default false, set ONLY by the test server via
// parallel_state {rx_hold} / {rx_drain_disable}). g_rxTestHold parks the pump's
// consumption by emulating a permanently-busy display FOR THE GATE ONLY (whitelisted
// carriers still flow, action_end markers hold) and feeds the stall count, so the
// 600-tick liveness floor trips on demand and (markers never idling) stays engaged - the
// genuine wedge the stage-2 hard-floor backstop must drain. g_rxDrainDisable forces the
// floor back to its legacy full-disable so the SAME build measures the pre-fix
// out-of-order burst (red) against the ordering-preserving drain (green). Never set
// outside the coop test harness -> production identical.
extern std::atomic<bool> g_rxTestHold;
extern std::atomic<bool> g_rxDrainDisable;
// TEST-ONLY: force the liveness floor to engage every tick regardless of the stall count,
// WITHOUT gating any packet - so a naturally-slow client (whose real display gates its
// action_end markers and idles between chains) runs under the engaged floor, the exact
// state the rare real stall produces. Lets the fixture measure the pre-fix out-of-order
// burst (rx_drain_disable) vs the ordered drain deterministically. Never set in production.
extern std::atomic<bool> g_rxForceFloor;
// The last `limit` packets the pump applied, oldest first: [{seq,state,unit}].
// Test-only introspection; `unit` is -1 for a packet that names no single unit.
Json::Value rxAppliedTrace(size_t limit);
// Test introspection: the front of the receive hold queue with each packet's chain stamp.
Json::Value rxHoldDump(size_t limit);
// Append a packet to the hold queue as if it had just arrived (TestServer only).
void rxInjectForTest(std::string&& payload);

// coop (explosion ordered-replay E2, test introspection): the last few chain_detonation
// tile positions THIS process has either SENT (parallel host, ExplosionBState.cpp's
// chained-spawn send site - its scan order) or APPLIED (parallel client, the
// chain_detonation handler below), as [x,y,z] tuples oldest-first. Process-local (each
// side is its own OpenXcom.exe/port in the test harness), so a fixture reads the host's
// list as its send order and the client's list as its receive order and diffs the two for
// exact positional equality - the count-only g_chainDetonationsSent/Applied above cannot
// distinguish "right count, wrong order" from a genuinely matching replay.
void chainDetonationListRecord(int x, int y, int z);
Json::Value chainDetonationListDump(size_t limit);

// ===== Geoscape sync conflation slot =====
// The two GeoscapeState::think() heartbeats are full-state, last-write-wins
// snapshots. Instead of FIFO-queuing every per-frame copy onto g_txQ (which
// overflows on a slow link), each channel keeps a single overwrite slot; the
// send thread emits the freshest one at whatever rate the link drains. Preserves
// update rate (no throttle) while eliminating the backlog.
enum CoopSnapSlot { SNAP_GEO_POSITIONS = 0, SNAP_GEO_TIME = 1, SNAP_DOGFIGHT = 2, SNAP_COUNT };

// Overwrite the conflation slot with the newest snapshot (thread-safe).
void enqueueSnapshot(CoopSnapSlot slot, std::string&& s);

// True if any conflation slot has an unsent snapshot (send thread wake check).
bool anySnapshotDirty();

// Pop one dirty conflation slot as a raw (unframed) payload, clearing its dirty
// flag; returns false if none pending. Used by the UDP transport, whose datagram
// path sends whole messages (the TCP path uses drainSnapshotsInto, which frames).
bool popSnapshot(std::string& out);

// Existing name kept for compatibility: this only enqueues to g_txQ.
// It does not have to mean that the active transport is TCP.
void sendTCPPacketStaticData(std::string data);

// Single place for enqueue logic.
// Returns false if queue is full, so caller may log/drop/retry.
bool enqueueTx(std::string&& s);

// Clears shared TCP/UDP transport queues and the updateCoopTask hold queue.
// Call this when leaving a multiplayer session before starting a new one.
void clearNetworkSessionQueues();

class Game;
class Ufo;
class SavedGame;
class BattleUnit;
class VoteMenu;
class ConfirmLandingState;
class NewBattleState;
class GeoscapeState;
class MissionSite;

// ===== Coop session lifecycle state =====

enum class CoopRole { None, Host, Client };

/**
 * Single owner of session-lifecycle state, replacing the scattered statics
 * that produced three flavors of the same missed/mis-ordered-reset bug.
 * Rules:
 *  - exactly TWO reset paths (resetSession / onClientDrop) - never clear
 *    fields ad hoc;
 *  - mutate through the named transitions where one fits, so every lifecycle
 *    change is searchable and logged (PRD-12 S4: the encoding is the mirrored
 *    booleans below; every multi-field or cross-file write funnels through a
 *    named, logged transition - there is no separate phase enum to drift from);
 *  - mutate on the main thread. The network threads keep signaling through
 *    onConnect and the pump/teardown translate. (The thread-side role writes
 *    and the transport-glue mirrors that predate this struct are kept raw and
 *    commented - see the residual list in the PRD-12 commit.)
 */
struct CoopSession
{
	CoopRole role = CoopRole::None;

	// what the lobby is for: 0 = legacy/new-battle (ready dance),
	// 1 = new co-op campaign (START CAMPAIGN), 2 = resuming a co-op save
	int lobbyMode = 0;
	// a client has passed every join gate (roster, password) and is attached;
	// onConnect==1 only means "listening", so this is the real presence signal
	bool clientInLobby = false;
	// players/teams locked (campaign started, resume began, or legacy ready
	// dance completed)
	bool sessionLocked = false;
	// the lobby UI has been dismissed - the session is considered live.
	// Defaults TRUE (historical isLobbyMenuClosed semantics: "no lobby open");
	// LobbyMenu's constructor clears it.
	bool lobbyClosed = true;
	// resume handshake: a client reported its world loaded (CoopState 62/64)
	bool resumeAck = false;
	// battle-save resume is two-phase: geoscape world first, then the battle
	// stream; set while phase two is still owed
	bool resumeBattlePending = false;
	// PRD-11 C8: names of clients that were actually SERVED a resume world blob
	// this resume cycle. Only an eligible acker gets the battle stream; a
	// registered-but-no-blob client (routed through fresh base building) must
	// not. Cleared together with resumeBattlePending.
	std::set<std::string> resumeBattleEligible;
	// set on clients when the host begins/resumes the campaign; releases the
	// "waiting for players" hold (CoopState 65)
	bool campaignBegun = false;
	// Custom Battle equipment gate. The host locks the selected craft before
	// either player may enter EQUIP CRAFT. The selected craft id then remains
	// authoritative for the lifetime of this multiplayer session.
	bool customBattleCraftLocked = false;
	int customBattleCraftId = -1;
	// issue #93: this client is rejoining a SKIRMISH (lobbyMode 0) session whose
	// battle is already running, so the battle blob it is about to load is a
	// REJOIN, not the start of a mission. One-shot: the load consumes it to send
	// the resume_ack that flips the host's freeze dialog to RESUME, and to hold
	// the client until the host presses it. The first battle of a skirmish loads
	// the very same blob key ("battleclient") and must not do either.
	bool skirmishRejoinPending = false;
	// host .sav awaiting a re-save once the fresh client blob arrives
	// (stale-embed race fix)
	std::string pendingHostSaveName;

	// --- named transitions (each logs; the log line is the lifecycle trace) ---
	void beginHosting();     // main menu/new game -> hosting a lobby
	void beginJoining();     // client connecting to a host
	void clientAttached();   // a client passed every join gate
	void campaignStarted();  // players/teams locked (START / campaign_start / ready-dance done)
	void sessionLive();      // waiting dialogs released - play begins/resumes
	void freeze();           // a registered player dropped mid-session (D5)
	void setRole(CoopRole r);// main-thread role change (setServerOwner)

	// --- multi-field / cross-file lifecycle writes funnelled here (PRD-12) ---
	void adoptResumeSave();          // a co-op save is loaded for resume (lobbyMode=2, unlock, clear ack)
	void armResumeHandshake(bool hasBattle); // resume/rejoin: clear ack, arm battle phase-two if a battle is loaded
	void markLobbyOpen();            // the lobby UI opened (lobbyClosed=false)
	void markLobbyClosed();          // the lobby UI dismissed (lobbyClosed=true)
	void armDeferredSave(const std::string& name); // host save deferred until the fresh client blob arrives
	void clearDeferredSave();        // deferred host save consumed/cleared
	void signalCampaignBegun();      // host began/resumed: release the client hold (campaignBegun=true)
	void consumeCampaignBegun();     // client consumed the release / cleared a stale one (campaignBegun=false)
	void lockCustomBattleCraft(int craftId); // freeze Custom Battle craft choice and unlock equipment UI

	// --- the ONLY reset paths ---
	void resetSession();     // full teardown / back to main menu
	void onClientDrop();     // host side: the campaign/lobby context survives
};

// Host-authoritative state for one multiplayer vote.
// Kept here because it is currently used only by connectionTCP and VoteMenu.
enum class VoteDecision
{
	Pending,
	Passed,
	Failed
};

/**
 * Host-authoritative state for one multiplayer vote.
 *
 * Votes are indexed by the co-op seat id. A strict majority is required:
 * 2/3 players, 3/4 players, 3/5 players, and so on.
 */
class VoteSession
{
public:
	static constexpr int NOT_VOTED = -1;
	static constexpr int VOTED_NO = 0;
	static constexpr int VOTED_YES = 1;

	bool active = false;
	bool finished = false;
	bool passed = false;
	std::uint64_t id = 0;
	std::string action;
	std::string title;
	std::string question;
	int totalPlayers = 0;
	int requiredYesVotes = 0;
	int starterSeat = -1;
	std::vector<int> votes;
	// Host-snapshotted names in seat order. The menu renders this copy instead
	// of asking each machine to reconstruct the roster independently.
	std::vector<std::string> playerNames;
	// The host owns the real deadline. Clients receive the remaining duration
	// and keep a local display deadline; vote_result remains authoritative.
	static constexpr std::uint32_t DEFAULT_TIMEOUT_MS = 30000;
	std::uint32_t deadlineTicks = 0;

	void clear()
	{
		active = false;
		finished = false;
		passed = false;
		id = 0;
		action.clear();
		title.clear();
		question.clear();
		totalPlayers = 0;
		requiredYesVotes = 0;
		starterSeat = -1;
		votes.clear();
		playerNames.clear();
		deadlineTicks = 0;
	}

	void start(
		std::uint64_t voteId,
		const std::string &voteAction,
		const std::string &voteTitle,
		const std::string &voteQuestion,
		int playerCount,
		const std::vector<std::string> &seatNames,
		int starter,
		std::uint32_t timeoutMs = DEFAULT_TIMEOUT_MS)
	{
		clear();

		active = true;
		id = voteId;
		action = voteAction;
		title = voteTitle;
		question = voteQuestion;
		totalPlayers = std::max(1, playerCount);
		requiredYesVotes = (totalPlayers / 2) + 1;
		starterSeat = starter;
		votes.assign(static_cast<std::size_t>(totalPlayers), NOT_VOTED);
		playerNames.assign(static_cast<std::size_t>(totalPlayers), std::string());
		const std::size_t nameCount = std::min(playerNames.size(), seatNames.size());
		for (std::size_t i = 0; i < nameCount; ++i)
		{
			playerNames[i] = seatNames[i];
		}
		deadlineTicks = SDL_GetTicks() + std::max<std::uint32_t>(1, timeoutMs);

		// Starting a vote is itself a YES vote. This lets any player request
		// the action without having to confirm it twice.
		castVote(starterSeat, true);
	}

	bool castVote(int seat, bool yes)
	{
		if (!active || finished || seat < 0 || seat >= totalPlayers)
		{
			return false;
		}
		if (votes[static_cast<std::size_t>(seat)] != NOT_VOTED)
		{
			return false;
		}

		votes[static_cast<std::size_t>(seat)] = yes ? VOTED_YES : VOTED_NO;
		return true;
	}

	int yesVotes() const
	{
		return static_cast<int>(std::count(votes.begin(), votes.end(), VOTED_YES));
	}

	int noVotes() const
	{
		return static_cast<int>(std::count(votes.begin(), votes.end(), VOTED_NO));
	}

	int votesCast() const
	{
		return yesVotes() + noVotes();
	}

	int remainingVotes() const
	{
		return std::max(0, totalPlayers - votesCast());
	}

	std::uint32_t remainingMilliseconds(std::uint32_t nowTicks = SDL_GetTicks()) const
	{
		if (!active || deadlineTicks == 0)
		{
			return 0;
		}

		// Signed subtraction is wrap-safe for deadlines less than 2^31 ms away.
		const std::int32_t remaining =
			static_cast<std::int32_t>(deadlineTicks - nowTicks);
		return remaining > 0 ? static_cast<std::uint32_t>(remaining) : 0;
	}

	bool timedOut(std::uint32_t nowTicks = SDL_GetTicks()) const
	{
		return active && remainingMilliseconds(nowTicks) == 0;
	}

	void setRemainingMilliseconds(std::uint32_t remainingMs)
	{
		deadlineTicks = SDL_GetTicks() + std::max<std::uint32_t>(1, remainingMs);
	}

	VoteDecision decision() const
	{
		if (!active || finished)
		{
			return finished && passed ? VoteDecision::Passed :
				(finished ? VoteDecision::Failed : VoteDecision::Pending);
		}

		if (yesVotes() >= requiredYesVotes)
		{
			return VoteDecision::Passed;
		}

		// Fail early when even every remaining player voting YES could no
		// longer reach the required strict majority.
		if (yesVotes() + remainingVotes() < requiredYesVotes)
		{
			return VoteDecision::Failed;
		}

		return VoteDecision::Pending;
	}

	void finish(bool votePassed)
	{
		active = false;
		finished = true;
		passed = votePassed;
	}
};

class connectionTCP
{
  private:
	std::thread _loopThread;
	std::thread _clientThread;
	std::thread _hostThread;
	// chat menu
	ChatMenu* _chatMenu = nullptr;
	Game* _game;
	// PRD-J01: process-single Game handle so the static seat accessors can
	// read the active roster (SavedGame::_coopPlayers). Set once in the ctor.
	static Game* _staticGame;
	Uint32 lastRandomClear = 0;
	void generateCraftSoldiers();
	bool _onTCP = false;
	bool _stop = false;
	bool _hostStop = false;
	bool _clientStop = false;
	void loopData();
	void startTCPClient();
	void startTCPHost();

	// Host-authoritative multiplayer vote. Votes are indexed by co-op seat,
	// so strict-majority calculation supports three or more players.
	VoteSession _activeVote;
	bool _voteRequestPending = false;
	std::uint64_t _voteSequence = 0;
	// Per-seat host-authoritative vote-start cooldown. Starting a vote writes a
	// 60-second deadline for that seat; other seats remain free to start votes.
	static constexpr std::uint32_t VOTE_START_COOLDOWN_MS = 60000;
	std::vector<std::uint32_t> _voteStarterCooldownUntil;
	VoteMenu* findVoteMenu(std::uint64_t voteId) const;
	void openVoteMenu();
	void updateVoteMenu();
	bool beginVoteAsHost(const std::string& action, const std::string& title,
		const std::string& question, int starterSeat);
	std::uint32_t voteStarterCooldownRemainingMs(int seat,
		std::uint32_t nowTicks = SDL_GetTicks()) const;
	void beginVoteStarterCooldown(int seat);
	void showVoteCooldownDialog(std::uint32_t remainingMs);
	void sendVoteCooldown(int seat, std::uint32_t remainingMs);
	void acceptVote(int seat, bool yes);
	void broadcastVoteStart();
	void broadcastVoteUpdate();
	void evaluateVote();
	void finishVote(bool passed);
	void executeVoteAction(const std::string& action);
	void readVoteSnapshot(const Json::Value& obj);
	std::vector<std::string> buildVotePlayerNames(int totalPlayers) const;

  public:
	// coop
	connectionTCP(Game* game);
	~connectionTCP();  
	bool _isMainCampaignBaseDefense = false;
	bool coop_end_turn = false;
	bool allow_cutscene = true;
	// research
	Json::Value waitedResearch;
	static bool _isChatActiveStatic;
	void initProfile(bool clientInBattle, bool inBattle);
	/// Push a state without burying an open "player joined" (Profile) popup.
	void pushKeepingProfileOnTop(State* state);
	/// Retire the "Connecting..." dialog when a connect attempt resolves.
	void closeConnectingDialog();
	long long getDateTimeCoop() const;
	void clearAllReceivedTCPPackets();
	void createLoopdataThread();
	void updateCoopTask();
	std::vector<std::string> splitVectorMod(std::string s, std::string delimiter);
	bool hasRequiredMods(const std::string& mod_hash);
	std::string getCurrentClientName();
	std::string getCurrentClientServer();
	void setCurrentClientServer(std::string servername);
	std::string getHostName();
	std::string getHostServer();
	void setHostName(std::string playername);
	void setHostServer(std::string servername);
	void setClientSoldiers();
	void deleteAllCoopBases();
	void updateAllCoopBases();
	void fixCoopSave();
	// coop
	// battle states
	void setConfirmLandingState(ConfirmLandingState* landing);
	void setNewBattleState(NewBattleState* battlesate);
	void setGeoscapeState(GeoscapeState* base_geo);
	NewBattleState* getNewBattleState();
	bool getLanding();
	void setSelectedCraft(Craft* selectedCraft);
	Craft* getSelectedCraft();
	void hostTCPServer(std::string servername, std::string port);
	void connectTCPServer(std::string ipaddress, std::string port);
	// Direct-LAN UDP transport (test/LAN): real connectionUDP threads on a
	// 127.0.0.1 password-derived session, no rendezvous. See the .cpp.
	void hostDirectLanUDP(std::string port, std::string player, std::string password);
	void joinDirectLanUDP(std::string ipaddress, std::string port, std::string localport,
	                      std::string player, std::string password);
	void onTCPMessage(std::string data, Json::Value obj);
	/// coop (parallel battlescape Phase 1 - per-unit state watermark): next_turn's
	/// per-unit bulk-apply loop, factored out of onTCPMessage so the TEST-ONLY
	/// synthetic replay lever (parallel_state {replay_last_next_turn:true}) can
	/// re-run exactly this loop against a stashed snapshot. Returns the unit ids
	/// whose stamped write was rejected by the watermark (the live caller uses
	/// this to also skip their coopApplyDeferredTurnStart()). Caller must ensure
	/// _game->getSavedGame()->getSavedBattle() is non-null.
	std::unordered_set<int> coopApplyNextTurnUnitStates(Json::Value& obj);
	/// coop (parallel battlescape Phase 1, TEST-ONLY SYNTHETIC RED lever): re-runs
	/// coopApplyNextTurnUnitStates on the last applied next_turn snapshot
	/// (g_lastNextTurnJson). Only reachable via the parallel_state TestServer
	/// command; never fires in shipped mode. No-op if no next_turn has applied yet.
	void coopDebugReplayLastNextTurn();
	void sendBaseFile();
	void sendMissionFile();
	/// issue #93: stream the RUNNING skirmish battle to a rejoining client.
	void streamSkirmishBattleToClient();
	void sendSaveProgressFile();
	bool cancel_connect = false;
	int getCurrentTurn();
	void loadHostMap();
	static bool getCoopStatic(); // is the player actually connected?
	void sendTCPPacketData(std::string data); // Send TCP packet data

	// Requests a multiplayer vote. The host creates the authoritative vote,
	// and the requesting seat is automatically counted as YES.
	bool requestVote(const std::string& action, const std::string& title,
		const std::string& question);
	// Casts the local seat's vote. Duplicate votes are rejected.
	bool castVote(std::uint64_t voteId, bool yes);
	bool hasVoteInProgress() const { return _activeVote.active || _voteRequestPending; }
	// Host-only Custom Battle transition. Once locked, the selected craft cannot
	// be changed and clients may open their local EQUIP CRAFT screen.
	bool lockCustomBattleCraft(std::size_t craftId);
	bool isCustomBattleCraftLocked() const { return session.customBattleCraftLocked; }
	int getLockedCustomBattleCraftId() const { return session.customBattleCraftId; }
	// Regression-harness accessors keep TestServer out of private members. The
	// session getter is read-only; the menu getter is used to press public controls.
	const VoteSession& getActiveVoteForTest() const { return _activeVote; }
	VoteMenu* getVoteMenuForTest(std::uint64_t voteId) const { return findVoteMenu(voteId); }
	// Deterministic harness hooks: exercise the real host timeout/cooldown paths
	// without making the regression suite sleep for 30 or 60 seconds.
	bool forceActiveVoteTimeoutForTest();
	void clearVoteStarterCooldownsForTest() { _voteStarterCooldownUntil.clear(); }
	std::uint32_t getVoteStarterCooldownRemainingForTest(int seat) const
	{
		return voteStarterCooldownRemainingMs(seat);
	}
	// Send a full-state geoscape snapshot via the conflation slot (last-write-wins,
	// never queued FIFO). slot is a CoopSnapSlot. Used by GeoscapeState::think().
	void sendCoopSnapshot(int slot, std::string data);
	// Reliable geoscape lifecycle: returns true (and updates the tracked set) when
	// the UFO/mission membership in the snapshot changed since the last call. The
	// conflation slot silently drops transient spawns/despawns, so the caller also
	// sends the snapshot on the reliable FIFO lane whenever this returns true. The
	// set rarely changes, so the extra reliable sends do not reintroduce the flood.
	bool geoMembershipChanged(const Json::Value& root);
	std::set<int> _lastGeoUfoIds;
	std::set<int> _lastGeoMissionIds;
	// Playtest: craft ids whose SHARED landing decision has been resolved (any seat
	// answered). Every seat is prompted; the losers' broker ConfirmLandingState polls
	// this in think() and closes itself. Marked by the host resolver / a land_close
	// broadcast; cleared when a fresh prompt for that craft goes out.
	std::set<int> _landingResolved;
	void markLandingResolved(int craftId) { _landingResolved.insert(craftId); }
	void clearLandingResolved(int craftId) { _landingResolved.erase(craftId); }
	bool consumeLandingResolved(int craftId)
	{
		auto it = _landingResolved.find(craftId);
		if (it == _landingResolved.end()) return false;
		_landingResolved.erase(it);
		return true;
	}
	static bool getHost();
	static int getHostSpaceAvailable();
	static void setHostSpaceAvailable(int _hostSpace);
	// coop (PRD-P6 pre-task): the receive gate, as a DEPTH COUNTER.
	//
	// It used to be `bool _coop_task_completed`. A bool cannot nest, and the
	// chains that hold it do: an InfoboxState opening and closing inside a shot
	// (InfoboxState ctor/dtor vs ProjectileFlyBState::init/deinit) wrote the gate
	// back OPEN while the projectile was still in flight, so a peer packet could
	// interleave into the middle of a local action chain. Depth 0 == "completed";
	// every holder takes a reference and gives it back.
	//
	// Writers go through setCoopTaskCompleted(false/true) (acquire/release) and
	// the two teardown sites through resetCoopTaskDepth(). Holders that can have
	// their init() re-entered (a BattleState is re-init'ed whenever something
	// pushed IN FRONT of it pops) must acquire at most once - they carry their own
	// `held` flag; see UnitWalkBState.
	int _coopTaskDepth = 0;
	/// Is no co-op action chain in progress (walk, turn, shoot, melee, psi, modal)?
	bool coopTaskCompleted() const { return _coopTaskDepth <= 0; }
	/// Current gate depth (0 = open). Test introspection / arbiter admission.
	int coopTaskDepth() const { return _coopTaskDepth; }
	/// false = acquire (++), true = release (-- , clamped at 0). Same call shape
	/// the pre-P6 bool API had, so every writer site reads unchanged.
	void setCoopTaskCompleted(bool completed);
	/// Teardown only: force the gate open, whatever is still holding it.
	void resetCoopTaskDepth() { _coopTaskDepth = 0; }
	size_t _coop_selected_craft_id = 0;
	std::string getPing();
	bool isCoopSession(); // is the co-op session created? (does not consider whether a player has joined)
	void setCoopSession(bool session);
	void setServerOwner(bool owner);
	static bool _coopCampaign;
	void setCoopCampaign(bool coop);
	static int _coopGamemode; // no mode = 0, PVE = 1, PVP = 2, PVP2 = 3, PVE2 = 4,
	static int coop_save_owner_player_id; // ID of the player who owns the co-op save 
	// PRD-J01: campaign economy model carried to a joining client during the
	// lobby handshake (before its save exists) so the type label can render.
	// 0 = Separate, 1 = Shared. Mirrors SavedGame::getCampaignType().
	static int _lobbyCampaignType;
	bool getCoopCampaign();
	// PRD-J01: true when the ACTIVE save is a SHARED co-op campaign. Every later
	// SHARED-gated behavior tests this; SEPARATE/solo return false.
	bool isSharedCampaign();
	// Static mirror for engine-level callers with no CoopMod instance (Craft capacity).
	static bool isSharedCampaignStatic();
	// PRD-J02: true for a SHARED client - a world replica the host streams. A
	// replica never builds its own world, never saves to disk, and never runs
	// the SEPARATE mirror machinery. (isSharedCampaign() && !host)
	bool isSharedReplica();
	// PRD-J02: serialize the host's authoritative world fresh and hand it to the
	// streamer (single-client resume-blob lane) so the connected client adopts
	// it as its replica. Host only; used at SHARED campaign start and resume.
	void streamSharedWorldToClient();
	// PRD-J10: serve a replica's shared_resync_request - stream the authoritative
	// world. No-op (the replica re-asks on its next mismatching checksum) if the
	// single-slot streamer is busy.
	//
	// issue #91: this used to also arm a one-shot "auto-release" flag read by the
	// resume_ack handler. It no longer does, and neither does the post-battle
	// restream: two restreams in a row shared the one flag and the second client
	// hold was never released. The handler now decides from the host's own state
	// (no wait dialog on the stack => the release is owed), which covers every
	// stream site instead of the two that remembered to arm a flag.
	void sharedResyncStream();
	// Seat = index into SavedGame::_coopPlayers (host = 0). N-player safe.
	static int localSeat();                 // this machine's seat
	static int seatCount();                 // active roster size
	static std::string seatName(int seat);  // player name for a seat
	// no mode = 0, PVE = 1, PVP = 2, PVP2 = 3, PVE2 = 4,
	static int getCoopGamemode();
	/// coop (PRD-P5): is the parallel shared player side live right now?
	/// PROTOCOL.md: `_enable_parallel_turns && gamemode in {1,4} && !hotseat`
	/// (plus an actual co-op session). While it is true both machines hold
	/// isYourTurn == 2 and `_isActivePlayerSync == getHost()` - the executor
	/// invariant every existing send/RNG guard is already written against.
	static bool parallelTurnActive();
	/// coop: is this machine a CLIENT during a parallel player side? PRD-P5
	/// used it as a blanket input gate; PRD-P6 replaced that with action
	/// intents and PRD-P8 replaced its last gate (END TURN) with the per-seat
	/// readiness toggle, so all it still answers is "am I the non-executor
	/// machine" - which the two classic UI-mirror send sites still ask.
	static bool parallelInputBlocked();

	// ---- coop (PRD-P6): action-intent arbitration -------------------------
	// The client never executes battle sim in parallel mode: it ships an
	// `action_intent`, the host validates + executes + broadcasts, and the
	// client displays the broadcast exactly as it displays a host action in
	// classic co-op. See PROTOCOL.md.

	/// HOST-owned. +1 per ADMITTED action (the host's own and every client
	/// intent). Stamped on `action_ack`; the broadcast packets carry it only
	/// from PRD-P7 on. Reset at each side boundary TOGETHER with
	/// peerDisplayAckedSeq - resetting one alone underflows P7's uint32
	/// backlog term `(_actionSeq - peerDisplayAckedSeq)` and blocks admission
	/// for the rest of the battle.
	static std::uint32_t _actionSeq;
	/// PRD-P7's display-flow term: the highest chain the PEER has reported having
	/// finished DISPLAYING (`action_done`). Lives next to _actionSeq so the two
	/// counters can never be reset apart. On a client this is instead the highest
	/// chain THIS machine has reported done, so the same readout means "how far
	/// the display has got" on either side.
	static std::uint32_t peerDisplayAckedSeq;
	/// HOST: the admitted chain that still owes the client an `action_end`
	/// (0 = none open). Stamped by stampAdmittedAction(), cleared when the marker
	/// goes out. PRD-P7.
	static std::uint32_t _openChainSeq;
	/// CLIENT: the chain seq the display is currently working through - the value
	/// the next `action_done` will carry. PRD-P7.
	static std::uint32_t _clientDisplaySeq;
	/// HOST (PRD-I0): the kind that was admitted as `_openChainSeq` ("walk",
	/// "shoot", "ai", ...). The arbiter's `_intentSlotKind` cannot serve: it is
	/// written only on the two CLIENT-intent admit paths, so the executor's own
	/// clicks and every AI chain would be attributed to whatever the last client
	/// happened to do. Purely a label on the sync-check ring entry.
	static std::string _openChainKind;
	/// CLIENT (PRD-I0): the `side_seq` the last consumed `action_end` marker
	/// named. NOT this machine's `_sideSeq`: `endTurn` is whitelisted and
	/// `action_end` is not, so the live token routinely runs ahead of the markers
	/// still queued behind the receive gate, and reporting under it would send
	/// the tail of a side's chains into the next side's key space.
	static std::uint32_t _clientDisplaySideSeq;
	/// HOST-owned (PRD-I0): the BOUNDARY pseudo-seq counter - one per side-close
	/// phase group, one per side start. Its OWN namespace, monotonic for the whole
	/// battle, deliberately NOT drawn from `_actionSeq`:
	///  * `_actionSeq` resets every side, so two boundary hashes taken either side
	///    of a reset would collide with the first real actions of the new side;
	///  * and, decisively, boundary seqs would enter PRD-P7's display-backlog term.
	///    A peer that predates PRD-I0 reports nothing for them, so the executor
	///    would sit at backlog 2 from the first side start and refuse every action
	///    for the rest of the battle. An additive field must never be able to wedge
	///    an older peer.
	static std::uint32_t _boundarySeq;
	/// HOST (PRD-I3 SEAM-2 HALF 2): true only for the duration of the
	/// neutral->player SavedBattleGame::prepareNewTurn tile-decay call, so the
	/// set_smoke_tile/set_fire_tile sends it drives carry `bnd:true`. Those flagged
	/// packets ride the ORDERED receive gate (not the always-consume whitelist), so
	/// the client's ai-seq hazard hashes sample pre-decay state. Set/cleared around
	/// the single call site; a mid-side explosion hazard is never inside the scope.
	static bool _coopBoundaryDecay;
	/// TEST-ONLY lever, default false, set ONLY by the test server
	/// (`hold_action_done`). While true the client PARKS its `action_done`
	/// reports instead of shipping them: the packet is unchanged, it just leaves
	/// later, so a test can hold the host's end-turn drain barrier open for as
	/// long as it likes instead of racing a ~200 ms round trip. Releasing emits
	/// the latest parked seq (`_clientDisplaySeq` is already the newest, and
	/// peerDisplayAckedSeq is deliberately NOT advanced while held, so one emit
	/// clears the whole backlog). `_heldActionDones` counts the reports parked
	/// since the hold was engaged - 0 means the client never finished displaying
	/// anything, i.e. the barrier was never exercised and a scenario asserting on
	/// it would be vacuous.
	static bool _testHoldActionDone;
	static std::uint32_t _heldActionDones;
	/// TEST-ONLY lever (`hold_action_done {boundary:true}`), default false. While
	/// true the client PARKS only its BOUNDARY `action_done` (coopEmitBoundaryDone),
	/// leaving the per-chain report flowing. That freezes the host's
	/// g_syncLastComparedBoundarySeq while per-chain acks keep the host committing
	/// and crossing boundaries - the exact "peer went dark on boundaries" condition
	/// A3's peer-liveness tripwire detects, forced deterministically.
	static bool _testHoldBoundaryDone;
	/// HOST (PRD-P9 3): the SDL tick `_openChainSeq` was stamped at, and whether
	/// the stuck-chain warning has already been logged for it. Diagnostic only -
	/// there is no distributed lock to break, so all this can do is say so once,
	/// with the arbiter state a bug report would otherwise have to guess at.
	static std::uint32_t _openChainTicks;
	static bool _openChainWarned;
	/// HOST (PRD-I3 SEAM-7 ii): an instant-kind chain (kneel/prime/medikit) whose
	/// replay packet has NOT been emitted yet. executeAction sends it AFTER the actor
	/// state settles; kneel()'s reaction-fire/FOV can fire coopChainChanged ->
	/// coopCloseActionChain in between, which would send the chain's action_end BEFORE
	/// the packet (and unstamped). While set, coopCloseActionChain holds off so the
	/// packet always precedes its own action_end on the wire. Cleared the moment the
	/// executor has emitted it (coopNoteInstantExecuted, from executeAction's tail).
	static bool _openChainInstantPending;
	/// HOST (wire-order Increment 7, SHAPE A): per-unit (tu, energy) captured at
	/// stampAdmittedAction (chain open), diffed at coopCloseActionChain to ship ONLY
	/// the units whose tu/energy changed during the chain as the marker's `regen`
	/// array. Generalizes abortPath's PRD-P9 walk-end tu/energy carry to every chain
	/// (incl. actor-less expl chains and in-chain multi-actor spend). unitId -> (tu,
	/// energy). Lever-gated (g_wireOrderState); empty/unused lever-off so the
	/// action_end packet stays byte-identical. DO-NOT-ADD morale: it is boundary-
	/// authored (endTurn death-morale cascade) and already covered by next_turn + the
	/// hit_unit bystander-morale carrier; a straddling pre-cascade morale absolute
	/// applied wire-after next_turn would MINT a new unitsRegen(morale) divergence.
	static std::unordered_map<int, std::pair<int, int>> _openChainRegenSnap;
	/// HOST-owned, +1 per side transition; the staleness token an intent
	/// carries. The client adopts the value stamped on the `endTurn` packet.
	static std::uint32_t _sideSeq;
	/// coop (PRD-P3 GAP-10 script-RNG seed-replay): the side-boundary RNG seed
	/// the host stamps on `endTurn` and the client adopts. newTurnUpdateScripts
	/// reseeds the global RNG to this around the mod newTurnUnit/newTurnItem script
	/// loops so both machines' randomChance/randomRange draw the same sequence.
	/// Defaults to the fixed coop base seed so turn-1 (pre-first-boundary) is defined.
	static std::uint64_t _scriptRngSeed;
	/// HOST: true from the END TURN press until the next player side opens.
	static bool _sideCommitInProgress;
	/// HOST: the one-slot pending intent (per seat; P6 executes on admission,
	/// so the slot records the intent whose chain is running).
	static std::uint32_t _intentSlotReqId;
	static int _intentSlotSeat;
	static std::string _intentSlotKind;
	/// HOST: why canAdmitAction() last refused ("" = it did not).
	static std::string _admitBlocked;
	/// HOST: why coopPendIntent() last refused to DEFER ("" = it took the input).
	/// PRD-P7; the counterpart of _admitBlocked for the pending-admit decision.
	static std::string _pendBlocked;
	/// CLIENT: monotonic req_id source (from 1, per battle).
	static std::uint32_t _clientReqSeq;
	/// CLIENT: the single pending slot. 0 = nothing outstanding.
	static std::uint32_t _clientPendingReqId;
	static std::string _clientPendingKind;
	static std::uint32_t _clientPendingSentTicks;
	/// CLIENT: the last `action_deny` it was sent - reason and warning key.
	/// The flash fades (and BattlescapeState::warning swallows it entirely off
	/// the player side), so this is the only stable readout of WHY an intent was
	/// refused. Test introspection; cleared with the request sequence.
	static std::string _clientLastDenyReason;
	static std::string _clientLastDenyWarning;

	// ---- coop (PRD-P7): pending-admit + display flow control ----------------
	/// One deferred input. The executor keeps at most one per seat: a newer input
	/// from the same seat REPLACES it and the replaced one is refused `busy`.
	struct CoopPendingIntent
	{
		std::uint32_t reqId = 0;   // 0 = the executor's own local click
		int seat = -1;
		std::string kind;
		std::string json;          // the serialized `action_intent` body
		bool local = false;
		/// PRD-P9 rider R4: SDL tick this slot was deferred at. The CLIENT gives
		/// up on an unanswered intent after 10 s, so a slot that outlives
		/// COOP_PEND_TIMEOUT_MS is refused rather than admitted into a seat that
		/// has already forgotten it.
		std::uint32_t deferTicks = 0;
	};
	static std::vector<CoopPendingIntent> _pendingAdmits;

	/// HOST: take this input as PENDING instead of refusing it, when the chain in
	/// the way is pure locomotion (BattlescapeGame::chainIsSkippable). Arms the
	/// fast-forward. Returns false when the caller must fall back to `busy`.
	static bool coopPendIntent(int seat, std::uint32_t reqId, const std::string& kind,
							   const std::string& intentJson, bool localOrigin);
	/// HOST: drop every pending input with a deny (default `busy`) - what reaction
	/// fire interrupting a fast-forwarded walk does, because the positions and TU
	/// the player clicked against may have moved a long way.
	static void coopDenyPendingIntents(const std::string& reason = "busy");
	/// HOST, main-thread tick: admit ONE pending input if the arbiter will take it.
	/// Deliberately not called from popState() - executing an action re-enters the
	/// state queue, and the drain point is in the middle of a pop.
	void coopAdmitPendingIntents();
	/// HOST: ship the `action_end` marker for the chain that has just drained, so
	/// the client can say when it has finished DISPLAYING it. Idempotent.
	static void coopCloseActionChain();
	/// HOST (PRD-I3 SEAM-7 ii): executeAction has emitted the current instant kind's
	/// replay packet - release the coopCloseActionChain hold (a no-op otherwise).
	static void coopNoteInstantExecuted();
	/// HOST (PRD-P9 3): log ONCE if the open chain has been running for over two
	/// minutes. Purely diagnostic; it frees nothing.
	static void coopCheckStuckChain();
	/// CLIENT: the single `action_done` emit point (PROTOCOL.md). No-op unless a
	/// newly displayed chain seq is outstanding.
	void coopEmitActionDone();
	/// HOST (PRD-I0): allocate a BOUNDARY pseudo-seq, remember this machine's
	/// bucket hashes for it, and ship the marker that tells the client to do the
	/// same. Rides `action_end` (with `"boundary": true`) rather than a new state
	/// string, precisely because `action_end` is NOT whitelisted: the client
	/// consumes it at receive-gate depth 0, which is what makes "hash after the
	/// boundary packets have been applied" true rather than hopeful.
	/// @a kind is "endturn" (the side-close phase group) or "sidestart".
	static void coopSendSyncBoundary(const char* kind);
	/// HOST (PRD-I0): remember that a boundary marker is owed. The side-close
	/// phases can still have explosion/death chains queued behind them, so the
	/// marker is sent from the main-thread tick once the executor is quiescent.
	static void coopArmSyncBoundary(const char* kind);
	/// HOST (PRD-I0), main-thread tick: send one armed boundary marker if idle.
	static void coopFlushSyncBoundary();
	/// HOST (wire-order Increment 6): flush a pending SIDESTART boundary EARLY - at the
	/// player-turn-start point BEFORE handlePanickingPlayer runs - so the ring captures the
	/// boundary STATE (post-side-close-drain, pre-start-of-turn panic/berserk), matching
	/// next_turn's snapshot and the client's wire-first-sight sample. Lever-gated
	/// (g_wireOrderState) and scoped to the sidestart kind; endturn boundaries keep the
	/// deferred !isBusy flush. Lever-off: no-op (the normal tick flush is unchanged).
	static void coopFlushSidestartBoundaryEarly();
	/// HOST (PRD-I0): boundary markers armed but not yet shipped.
	static std::vector<std::string> _pendingBoundaries;
	/// coop (PRD-I3 Option D-lite): the parallel client defers its NEUTRAL->PLAYER
	/// turn-machine advance off the whitelisted endTurn packet and flushes it at the
	/// gated next_turn apply, so _turn/_side follow the display. _turnAdvanceDeferred
	/// is the pending flag (exposed on parallel_state); _hostShipsNextTurnFields learns
	/// from the first fields-bearing next_turn whether the host authors turn/side (an
	/// old host never does, so the client keeps the legacy inline advance).
	static int _turnAdvanceDeferred;
	/// coop (PRD-I3 rider): MONOTONIC count of NEUTRAL->PLAYER advance deferrals this
	/// battle. The transient _turnAdvanceDeferred bool arms and clears inside one
	/// next_turn window, which a test poll can miss; this only rises, so a test reads
	/// a before/after delta instead of racing the flag. Reset with the flag on a full
	/// resetActionArbiter (battle-scoped).
	static int _turnAdvanceDeferredCount;
	static bool _hostShipsNextTurnFields;
	/// CLIENT (PRD-I0): answer a boundary marker with this machine's buckets.
	void coopEmitBoundaryDone(std::uint32_t bseq);
	/// CLIENT (PRD-I0): answer an `action_end` whose side has already closed here,
	/// WITHOUT moving either display watermark. See the call site: adopting such a
	/// marker's seq freezes `_clientDisplaySeq` above the new side's whole range
	/// and wedges the executor's display-backlog term for the rest of the battle.
	void coopEmitStaleActionDone(std::uint32_t seq, std::uint32_t sideSeq);

	/// May the executor start a new action chain right now? PROTOCOL.md
	/// "Ordering invariants" 3: no BattleState queued, receive gate open, no
	/// side commit under way, and (PRD-P7) the client's undisplayed backlog
	/// below 2.
	static bool canAdmitAction();
	/// Stamps an admitted action: ++_actionSeq, returns the new value. @a kind
	/// (PRD-I0) labels the chain for the sync-check ring; it is a diagnostic
	/// label only and nothing branches on it.
	static std::uint32_t stampAdmittedAction(const std::string& kind = std::string());
	/// coop (PRD-I1): tag a whitelisted outcome packet (@a root) with the chain
	/// and side it belongs to, so the client defers it until that chain opens
	/// locally instead of letting it overtake its own opener. No-op outside an
	/// admitted/AI chain on the parallel host (_openChainSeq == 0).
	static void coopStampChainSeq(Json::Value& root);
	/// coop (PRD-I3 SEAM-3 a): if the parallel host is running an explosion with
	/// NO open admitted chain, open one (kind @a kind) so its destroy_tile/hazard
	/// outcome carries a seq and the client holds it on the I1 apply-before-hash
	/// gate instead of applying it immediately (the loose-destroy terrain straddle).
	/// No-op off the parallel host or when a chain is already open.
	static void coopStampLooseOutcomeChain(const char* kind);
	/// coop (PRD-I3 SEAM-2 HALF 2): open/close the boundary-decay scope around the
	/// neutral->player prepareNewTurn call. While open, coopStampBoundaryOrigin()
	/// tags a host tile-hazard send with `bnd:true`.
	static void coopSetBoundaryDecay(bool active);
	/// coop (PRD-I3 SEAM-2 HALF 2): tag @a root with `bnd:true` when a host
	/// set_smoke_tile/set_fire_tile send is the boundary-phase decay, so the client
	/// gates it in FIFO instead of whitelisting it. No-op (field absent) otherwise -
	/// additive, an older peer ignores it and keeps the whitelist behaviour.
	static void coopStampBoundaryOrigin(Json::Value& root);
	/// Battle start / side boundary / teardown: counters and slots back to a
	/// known state. `fullReset` also zeroes the side and request sequences.
	static void resetActionArbiter(bool fullReset);
	/// CLIENT: ships an intent and takes the pending slot (a second input
	/// REPLACES the slot - the stale ack is then ignored by req_id).
	bool sendActionIntent(Json::Value intent, const std::string& kind);
	/// CLIENT: drops the pending slot (ack received, deny received, timeout).
	static void clearClientPendingIntent();
	/// CLIENT: forgets the last deny (test introspection reset).
	static void clearClientLastDeny();
	/// Main-thread tick: the 10 s pending-intent timeout.
	void tickActionIntents();
	/// Flashes a translatable key on the battlescape warning widget, if there
	/// is a battlescape. The deny UX; survives thanks to PRD-P5 dropping the
	/// persistent off-turn banners that used to squat on that widget.
	void flashBattleWarning(const std::string& key);

	// ---- coop (PRD-P8): end-turn readiness gate ---------------------------
	// A parallel side has no single owner, so it cannot be closed by one
	// player's button press. Every seat arms its readiness (explicitly, or
	// automatically once it has nothing left to command) and the executor
	// commits the side when the last one arms. PROTOCOL.md
	// `end_turn_ready` / `end_turn_tally` - standalone messages, NOT VoteSession.

	/// Seat-indexed EXPLICIT readiness (an END TURN press). Host-authoritative;
	/// a client holds the echoed tally plus its own optimistic bit.
	static std::vector<bool> _endTurnReady;
	/// Seat-indexed AUTO readiness: "this seat has no live commandable unit
	/// left". Derived, never pressed - recomputed by the executor every tick, so
	/// a death, a mind-control flip and a gift all clear/raise it with no
	/// per-site hook to forget.
	static std::vector<bool> _endTurnAuto;
	/// The `side_seq` the currently-held tally belongs to. A tally for a
	/// DIFFERENT side is adopted silently (no peer flash) - the all-clear that
	/// follows a commit is not somebody cancelling.
	static std::uint32_t _endTurnTallySideSeq;
	/// HOST: character signature of the last `end_turn_tally` put on the wire
	/// ("<side_seq>:<seats>:" then one of R/A/. per seat), so the tick echo only
	/// builds and sends a packet when something actually changed.
	static std::string _endTurnTallySent;
	/// HOST: why coopCheckSideCommit() last refused ("" = it did not, or it
	/// committed). Test introspection.
	static std::string _commitBlocked;

	/// Grows both readiness vectors to seatCount(). Cheap; called before any read.
	static void ensureEndTurnSeats();
	/// Everything a side boundary / teardown must forget. Lives inside
	/// resetActionArbiter() so it can never be reset apart from the arbiter.
	static void resetEndTurnReady();
	/// Is `seat` ready by either route?
	static bool endTurnSeatReady(int seat);
	/// How many seats are ready (either route) - the tally UI's numerator.
	static int endTurnReadyCount();
	/// Are ALL seats ready? (the commit's first term)
	static bool endTurnAllReady();
	/// HOST: re-derive `_endTurnAuto` from the live roster.
	static void recomputeEndTurnAuto();
	/// HOST: put `end_turn_tally` on the wire if the tally changed since the last
	/// send. The "echo after EVERY change" of PRD-P8 §1, driven from the tick so
	/// no mutation site can forget it.
	void sendEndTurnTallyIfChanged();
	/// HOST: this seat just had an action ADMITTED, so its explicit ready is
	/// stale (it clearly did not mean "I am done"). Auto readiness is derived and
	/// is left alone.
	static void noteSeatActed(int seat);
	/// LOCAL: the END TURN button in parallel mode. Flips this machine's own
	/// readiness; a client ships `end_turn_ready`, the host just updates the
	/// tally it owns.
	void toggleEndTurnReady();
	/// HOST, main-thread tick: close the side once every seat is ready, the
	/// arbiter is idle and the peer's display backlog has drained.
	void coopCheckSideCommit();

	void createCoopMenu();
	static void sendTCPPacketStaticData2(std::string data);
	void writeHostMapFile2();
	void writeHostMapFile();
	bool writeHostMapSaveProgressFile();
	void writeHostMapLoadProgressFile();
	// PRD-06: write the armed deferred host save exactly once (embedding the
	// current client blob) and disarm. Used by both the completed round-trip
	// and the wait-dialog CANCEL path. No-op if nothing armed / a battle is live.
	void writePendingHostSave();
	bool inventory_battle_window = true; // Do not use inventory if another player joins a saved game
	static bool getServerOwner();
	bool ready_coop_battle = false; // notify the other player that the co-op mission is starting
	bool ready_coop_save_progress = false; // Notify the other player that progress saving is starting
	std::vector<Soldier*> coopSoldiers;
	std::string current_base_name = "";
	int64_t coopFunds = 0; // Stores the current player’s funds
	int64_t playersFunds = 0; // Stores the funds of all players
	int64_t playersCrafts = 0;  // Stores the crafts of all players
	int64_t playersBases = 0; // Stores the bases of all players
	void setHost(bool host);
	static bool playerInsideCoopBase; // is the player really in another player's base?
	bool coopMissionEnd = false; // is the co-op mission completed?
	Json::Value _jsonTargets, _jsonDamages, _jsonInventory, jsonAddedCoopItems;
	void syncCoopInventory();
	static bool coopInventory;
	int _pathLock = -1;
	void setPathLock(int lock);
	bool _waitBC = false; // is the client ready in battle?
	bool _waitBH = false; // is the host ready in battle?
	bool _battleWindow = false; // end turn screen
	static bool _battleInit; // when both have joined and are ready for battle, initialize
	int _playerTurn = 0; // 0 = no one, 1 = team, 2 = your, 3 = waiting, 4 = spectator mode
	void setPlayerTurn(int turn);
	int getPlayerTurn() const { return _playerTurn; }
	void sendFile();
	// is the player actually connected?
	int isConnected();
	void setConnected(int state);
	void disconnectTCP(bool isMain = false);
	ChatMenu* getChatMenu();
	void setChatMenu(ChatMenu* menu);

	int unitstatusToInt(UnitStatus status);
	UnitStatus intToUnitstatus(int status);
	int ufostatusToInt(Ufo::UfoStatus status);
	Ufo::UfoStatus intToUfostatus(int status);
	int ItemDamageRandomTypeToInt(ItemDamageRandomType type);
	ItemDamageRandomType intToItemDamageRandomType(int type);
	int ItemDamageTypeToInt(ItemDamageType type);
	ItemDamageType intToItemDamageType(int type);
	int InventoryTypeToInt(InventoryType type);
	InventoryType intToInventoryType(int type);
	int SoldierRanktoInt(SoldierRank rank);
	SoldierRank intToSoldierRank(int rank);

	// coop projectiles
	Json::Value _coopProjectilesClient;
	Json::Value _coopProjectilesHost;

	Json::Value _coopEndPath = Json::nullValue;

	bool _coopInitDeath = false;
	bool _coopWalkInit = false;
	bool _coopAllow = true;

	// coop (Class-A soak wedge fix): the auto-shot pacing wait in
	// ExplosionBState::think() (the non-host client parking a multi-shot replay on
	// `_hasHitUnit == 1` until the host's flip packet lands). Set true while that
	// state is waiting, false the instant it is released. It is the ONE display
	// state that can hold the receive gate (via the ProjectileFlyBState beneath it,
	// _coopInitDeath) for the whole rest of the battle when the flip never arrives -
	// a client/host shot-count divergence, likeliest on hazard-heavy turns where a
	// terrain-chain ExplosionBState reads the same shared pacing flag. updateCoopTask
	// counts consecutive game-loop ticks it stays set (g_rxPacingStallTicks) and,
	// past kRxPacingForceDrainTicks, raises _coopForceDrainReplay so the state can
	// advance instead of starving forever. Counted at the game-loop rate, NOT the
	// setStateInterval-throttled think() rate, so the escape is wall-time bounded
	// regardless of the client's draw speed.
	bool _coopPacingWait = false;
	/// Set by updateCoopTask when _coopPacingWait has been held past the stall
	/// floor; consumed (and cleared) by ExplosionBState::think(), which force-releases
	/// the pacing wait. A last-resort liveness escape, never armed under normal lag.
	bool _coopForceDrainReplay = false;
	/// Monotonic count of force-drains (introspection / regression guard). Expected
	/// 0 across a clean soak; a non-zero value in the field means a real wedge was
	/// broken, which A3's peer-liveness tripwire would have surfaced too.
	std::uint32_t _coopForceDrainCount = 0;

	int _coopPVPwin = 0; // 0 = not set, 1 = xcom, 2 = ufo

	bool _clientPanicHandle = false;

	// coop (parallel turns): click-sync window for the "Please wait for <player>'s
	// action" banner. A BUSY action_deny arms this to N frames so the banner is up
	// on the exact deny even if a mirror-packet gap left this machine momentarily
	// not-busy; BattlescapeState::updateCoopWaitBanner() reads and decrements it.
	int _coopWaitDenyTicks = 0;

	static bool _isActiveAISync;

	static bool _isActivePlayerSync;

	// coop (#162 / 056b500db reconciliation): set true when the peer sent a
	// `coop_leaving` before its socket closed - i.e. it pressed OK on a skirmish
	// debriefing and left gracefully, which is NOT a drop. The disconnect-notice
	// gate reads it so a graceful leave stays silent while an ABRUPT drop (no
	// `coop_leaving`) still raises the notice. One-shot per session; reset at
	// every disconnectTCP teardown and on a fresh client attach.
	static bool _peerLeftCleanly;

	bool _onClickClose = false;

	int _currentAmmoID = -1;
	std::string currentAmmoType = "";

	bool _enable_research_sync = true;

	static bool _enable_time_sync;

	static bool _enable_reaction_shoot;

	static bool _enable_other_player_footsteps;

	static bool _enable_host_only_time_speed;

	static bool _enable_xcom_equipment_aliens_pvp;

	static bool _unbalanced_craft_soldiers_limit;

	// coop (PRD-P5): the SESSION's parallel-turns mode. Mirrors the HOST's
	// Options::EnableCoopParallelTurns across the COOP_READY_HOST handshake, so
	// both machines answer parallelTurnActive() identically for the whole
	// session. A peer that never sends the key (old build) leaves this false =
	// classic mode, which is the free backwards-compatibility degrade.
	static bool _enable_parallel_turns;

	int walk_end_unit_id = -1;

	bool AbortCoopWalk = false;

	// time
	static int _weekday;
	static int _day;
	static int _month;
	static int _year;
	static int _hour;
	static int _minute;
	static int _second;

	static int monthsPassed;
	static int daysPassed;

	int _AIProgressCoop = -1;
	bool _AISecondMoveCoop = false;
	int _coopEnd = 0;
	int _psi_target_id = -1;

	int _melee_target_id = -1;
	int _melee_hit_number = -1;

	// coop (PRD-P3 GAP-4b): parked hit/miss decisions, FIFO. The melee sender rolls
	// in MeleeAttackBState::init (before the ExplosionBState it pushes can roll it)
	// and ships the boolean on the SAME packet, so the receiver has the answer
	// parked before its own chain starts - a follow-up packet would race it.
	// TileEngine::meleeAttack pops one; BA_CQB never touches this queue.
	std::vector<int> _meleeResults;
	// Same shape for the BA_SELF_DESTRUCT chance: the host rolls it in
	// BattleUnit::damage (which is already host-only) and ships it on the existing
	// selfDestruct packet, because ExplosionBState::init - where the roll used to
	// live - runs after that packet has already gone out.
	std::vector<int> _selfDestructResults;
	// coop (wire-order report alignment, Increment 3 / A2): display-side copies of the
	// two parked-outcome queues above. Lever-on, the parallel CLIENT's receiver-park
	// writes HERE (not the canonical vectors) and its display replay consumes from here,
	// so next_turn's state-half clear of the canonical queue (increment 5, at RX arrival)
	// cannot starve a still-queued melee / self-destruct replay. Empty lever-off and on
	// the host, so the display-first consume (TileEngine::meleeAttack, ExplosionBState)
	// falls through to the canonical queue byte-identically.
	std::vector<int> _meleeResultsDisplay;
	std::vector<int> _selfDestructResultsDisplay;
	// coop (PRD-P3 GAP-4b): close-quarters outcome shipped with the shot packet.
	// The peer does not run the CQB check at all (its redirect already rides the
	// packet's target coords); it only applies the defender's cost.
	bool _cqbBlocked = false;
	int _cqbDefenderId = -1;

	bool pve2_init = false;

	std::string other_time_speed_coop = "";
	// coop: teammate's last-reported geoscape time-speed id ("_btn5Secs".."_btn1Day"),
	// "" if unknown. Unlike other_time_speed_coop (consumed/cleared every timeAdvance),
	// this persists so the geoscape UI can show which speed the ally has selected.
	std::string peerTimeSpeedId = "";
	// coop: wall-clock ms of the last "time" heartbeat received from the peer,
	// updated on both sides. A "time" packet is emitted every GeoscapeState::think()
	// the peer spends on the geoscape; if it goes stale the peer is away
	// (base/options/popup/etc.). The host uses this to freeze the shared clock, and
	// both sides use it to dim the ally marker to yellow. Written on the packet-handler
	// thread, read on the main thread, hence atomic.
	std::atomic<Uint32> lastPeerTimePacketMs{0};
	// coop: which geoscape location the teammate is looking at, for the ally marker.
	// -1 = on the geoscape (use peerTimeSpeedId); 0..5 = a toolbar sub-screen index
	// (Intercept/Bases/Graphs/Ufopaedia/Options/Funding). Reset to -1 whenever a
	// "time" packet arrives (those are only sent from the geoscape).
	std::atomic<int> peerFocusScreen{-1};

	int show_coop_mission_popup = -1;

	// issue #78: authoritative mission-site id set from the last SHARED geoscape
	// snapshot. Written on the packet-handler thread; the actual despawn of
	// replica sites absent from this set happens on the main thread
	// (GeoscapeState::think, which only runs with the geoscape on top, so no
	// popup can be holding a dangling MissionSite*) - hence the mutex.
	std::mutex sharedLiveSiteIdsMutex;
	std::unordered_set<int> sharedLiveSiteIds;
	bool sharedLiveSiteIdsValid = false;

	std::string show_coop_ufo_popup_type = "";
	std::string show_coop_ufo_popup_race = "";
	std::string show_coop_ufo_popup_altitude = "";

	// Pending peer UFO-detected alerts. This used to be the single type/race pair above,
	// which was lossy twice over: a second detection in the same window overwrote the
	// first (alert silently lost), and matching on type+race alone could pop the dialog
	// for the WRONG UFO of the same race/type. Queued, and carrying the peer's ufo id so
	// the match is exact in SHARED (shared world -> identical ids).
	struct CoopUfoAlert { int ufoId = -1; std::string type; std::string race; };
	std::vector<CoopUfoAlert> coopUfoAlerts;
	static const size_t kMaxCoopUfoAlerts = 16; // bound: drop oldest, never grow forever

	bool show_coop_monthly_report = false;

	int fundingDiffCoop = -1;
	int ratingTotalCoop = -1;
	int lastMonthsRatingCoop = -1;

	// PRD-J04: authoritative monthly settlement carried on the extended
	// monthly_report packet (SHARED). A replica overwrites its own recomputed tails
	// with these in time1MonthCoop, so funds/maintenance never drift from the host.
	bool sharedMonthlyPending = false;
	int64_t sharedMonthlyFunds = 0;
	int64_t sharedMonthlyMaintenance = 0;
	int64_t sharedMonthlyIncome = 0;
	int64_t sharedMonthlyExpenditure = 0;
	int sharedMonthlyResearchScore = 0;

	std::vector<std::string> _happyListCoop, _sadListCoop, _pactListCoop, _cancelPactListCoop;

	Json::Value _coopFacility;

	Json::Value _deleteCoopFacility;

	Json::Value _soldier_stats;

	Json::Value _battle_stats;

	bool show_briefing_state = false;

	std::vector<Position> _trajectoryCoop;

	std::string _debriefing_coop_title = "";

	std::string load_state = "Please wait";

	static bool moveCoopItems;

	int _selectedItemID = -1;
	std::string _selectedItemType = "";

	bool _coop_promotions = false;

	int _hasHitUnit = -1;

	bool openMultipleTargetsMenu = false;

	static bool no_bases;
	static bool isCoopBaseLoading;

	// hotseat
	static bool _isHotseatActive;
	static bool _isHotseatReactionFireEnabled;
	bool _changeHotseatTurn = false;
	bool _isHotseatAlienTurn = false;
	Json::Value _discoveredTilesAlienTurn;
	Json::Value _discoveredTilesXComTurn;
	bool _firstAlienInit = false;

	// MissionStatistics
	Json::Value toJson(const std::map<int, int>& m);
	std::map<int, int> fromJson(const Json::Value& j);
	Json::Value _missionStatisticsCoop = Json::nullValue;

	// inventory
	static bool show_inactive_player_inventory;

	// pause
	static bool pauseSound;

	// LOAD_PROGRESS
	bool _isLoadProgress = false;

	// Transport scratch only: peer base/battlescape payloads plus the served
	// client-world blobs for the CURRENT session. Never a permanent save
	// store - the host .sav embed (coopClientSaves) is the durable copy, and
	// SavedGame::load redefines the served set from it on every load. (Same
	// intent as the fixes branch: temp data and permanent saves stay
	// strictly separate.)
	// Stores coop files in a hash map instead of separate files in the host folders
	static std::unordered_map<std::string, std::string> coopFilesHost;
	// Stores coop files in a hash map instead of separate files in the client folders
	static std::unordered_map<std::string, std::string> coopFilesClient;
	// Guards both blob maps: the loopData streamer thread reads them while the
	// main thread stores/erases entries. Hold only around map access; copy the
	// blob out before any long work.
	static std::mutex coopFilesMutex;
	static bool hasCoopFile(const std::string& key);
	// Canonical world-blob keys, scoped by the current saveID:
	// host_<saveID>_<clientName>.data / client_<saveID>_<hostName>.data
	static std::string hostBlobKey(const std::string& clientName);
	static std::string clientBlobKey(const std::string& hostName);
	// Newest stored world blob for a given client, matched by EXACT player-name
	// field across any saveID (the host re-mints saveID on every save, so the
	// stored key's id can lag the current one). Returns nullptr if none. Blob
	// identity comes from the caller's roster, never from reverse-parsing keys.
	// CALLER MUST HOLD coopFilesMutex; the returned pointer is valid only while
	// that lock is held.
	static const std::string* findHostClientBlob(const std::string& clientName);
	// Single authority: may this machine read/write local .sav files right now?
	// Truth table: solo play -> yes; coop host -> yes; coop client -> no.
	// Every local save/load gate and Load/Save button-visibility decision must
	// route through this so the rule lives in one place (PRD-08 tunes the host
	// case later by editing only this function).
	static bool localSavesAllowed();
	// issue #79: the campaign is OVER on this machine (won or lost) - the
	// active save carries an ending. A peer leaving after that is not a drop
	// to recover from, it is two players walking away from a finished game, so
	// every "the other player vanished" notice and freeze is suppressed.
	static bool campaignEnded();
	// The skirmish twin of campaignEnded(): a NEW BATTLE > COOP mission has run
	// and finished, so the only thing the world is still holding up is the
	// debriefing each player is reading. Closing that debriefing ends the world
	// (DebriefingState::btnOkClick -> GoToMainMenuState for a monthsPassed == -1
	// save), so a peer leaving now is EXPECTED - they closed theirs first - not a
	// drop to report or to re-open a lobby for.
	static bool skirmishMissionOver();
	// coop (#162): is a skirmish DebriefingState open right now (monthsPassed == -1
	// + a DebriefingState on the state stack)? skirmishMissionOver() stays true
	// through the post-OK menu transition too, so this narrower predicate is what
	// separates "the peer dropped while I am reading results" (show the notice)
	// from "I already dismissed my debrief and am on my way to the menu" (silent).
	static bool debriefOpen();
	// PRD-08 C7: may this machine LOAD a local save RIGHT NOW? False whenever a
	// live coop session is attached (host OR client) - loading mid-session forks
	// the served world silently. True when solo / after the session ends (the
	// lobby resume/rejoin flows are the sanctioned way to change worlds).
	static bool localLoadsAllowed();
	// One authority for the packet that creates/refreshes a client world
	// (fields: state=campaign_start, difficulty, gamemode, saveID, players[]).
	// Built identically by host lobby start, resume-no-blob, and the
	// request_load_progress no-blob fallback.
	static Json::Value buildCampaignStartPacket(const SavedGame* save);
	// STATELESS campaign-context check derived from the live save (a co-op
	// campaign world is loaded). Prefer this over session.lobbyMode for
	// host-side routing decisions: lobby mode is transport-lifecycle state.
	bool inCoopCampaignContext() const;

	// The single owner of session-lifecycle state: see CoopSession above the
	// class. Mutate via its named transitions / the two reset methods.
	static CoopSession session;

	// Reason string from the last lobby_join_refused, shown by the refusal
	// dialog (CoopState 63).
	static std::string joinRefusalReason;

	// PRD-J10: already-translated text of the last rejected SHARED command, shown by
	// the single failure dialog (CoopState COOP_DLG_SHARED_FAIL). Written only by
	// SharedEcon::showFail - same idiom as joinRefusalReason above.
	static std::string sharedFailReason;

	// save
	static bool saveError;
	static long long saveID;

	// password
	static bool isPasswordRequired;
	static std::string password;

	// lobby menu (legacy ready-dance fields; campaign lobbies don't use them)
	static bool isPlayerReady;
	static bool isPlayersReady;
	static int LobbyFileStatus;
	static int lobby_timer;
	// PRD-11 C13: one-shot signal from the network thread that the host replied
	// "busy" to a request_load_progress. The client's load-wait dialog (CoopState
	// 52) consumes it and schedules a retry.
	static bool loadProgressBusy;
	static bool forceCloseCoopStateMenu;
	static bool forceClosePasswordCheckMenu;

	// other
	static int manuallyAddedServerRemoveID;
	static bool canRemoveManuallyAddedServer;
	static bool isInfoboxClosed;

	// True when this machine may transfer control of the given live Battlescape
	// unit. This deliberately does not depend on whose turn it is: players may
	// gift their own soldiers while another player is acting.
	bool canGiftBattleUnit(const BattleUnit* unit) const;
	// Keeps a local gift-selection separate from SavedBattleGame::selectedUnit.
	// The normal selection belongs to the active tactical turn and is not updated
	// by an off-turn player's left click. mapClick updates this local selection
	// whenever this machine clicks one of its own giftable soldiers.
	void setGiftSelectedBattleUnit(BattleUnit* unit);
	BattleUnit* getGiftSelectedBattleUnit() const;
	void clearGiftSelectedBattleUnit();
	// Transfers a deployed unit to another seat. Campaign soldiers use the
	// permanent gift path; skirmish-only units use a battle-only control flip.
	void giftBattleUnit(BattleUnit* unit, int newOwnerId, bool broadcast);
	// Re-evaluates this machine's local tactical roster after a transfer. If no
	// living local soldiers remain, Battlescape enters spectator mode
	// immediately. Receiving a soldier restores control from spectator mode.
	void refreshBattleGiftControlState();

	// Permanently gifts a soldier to another player (0 = host, 1 = client).
	// Follows the guest-soldier model: a soldier's object lives in its OWNER's
	// save, tagged with coopBase = the station base's coop id when that base
	// belongs to the other player (-1 when stationed at one of the owner's own
	// bases). The soldier is serialized, removed from the giver's save and
	// recreated in the receiver's save, keeping the same station base - so it
	// stays "in" the base it was in, and shows up when the new owner views
	// that base. During battle only the control flags flip immediately; the
	// physical move is queued and runs after the mission ends. A newer,
	// ownership-validated transfer supersedes an older pending destination.
	void giftSoldier(Soldier* soldier, int newOwnerId, bool broadcast);
	// Completes queued in-battle gifts once no battle is active. Must run
	// before the post-battle coop cleanup (GeoscapeState calls it first).
	void processPendingSoldierGifts();

  private:
	// Serializes the soldier (with its station base id) and sends the
	// physical-gift packet to the peer.
	void sendSoldierGiftPacket(Soldier* soldier, int newOwnerId);
	// Erases the soldier pointer from every base roster (including the
	// SoldiersState/CraftSoldiersState base_oldsoldiers snapshots).
	void removeSoldierFromLocalBases(Soldier* soldier);
	// In-battle gifts waiting for the mission to end. Snapshot the craft id and
	// type while the battle world is still alive: Soldier::getCraft() may keep a
	// non-null pointer to a Craft that has already been destroyed or replaced by
	// the time processPendingSoldierGifts() runs. Dereferencing that stale Craft*
	// after mission teardown is a use-after-free and can crash in Craft::getType().
	struct PendingSoldierGift
	{
		Soldier* soldier;
		int newOwnerId;
		int craftId;
		std::string craftType;

		PendingSoldierGift(Soldier* soldier_, int newOwnerId_, int craftId_, const std::string& craftType_)
			: soldier(soldier_), newOwnerId(newOwnerId_), craftId(craftId_), craftType(craftType_)
		{
		}
	};
	std::vector<PendingSoldierGift> _pendingSoldierGifts;
	// Soldiers gifted away are parked here instead of deleted: UI states
	// (sort snapshots, open dialogs) may still hold pointers to them.
	std::vector<Soldier*> _giftedSoldiers;
	// Ids of soldiers gifted away this session. A stale copy of one of
	// these can resurrect when the pre-visit "basehost" snapshot is restored;
	// the sweep in processPendingSoldierGifts() parks exactly those (and
	// nothing else - legacy saves carry unrelated ownerPlayerId values).
	std::unordered_set<int> _giftedAwaySoldierIds;
	// Counter feeding the unique per-packet gift id, plus the in-memory
	// duplicate-delivery guard (sufficient now: the host's save is the single
	// authority, so packets are never re-sent across sessions).
	int _giftSendCounter = 0;
	// Mints the next outgoing gift packet id. Seat-keyed so two senders
	// never share an id space; see the definition in connectionTCP.cpp.
	long long nextGiftXferId();
	// Local-only id of the soldier last left-clicked for gifting. It must not use
	// SavedBattleGame::_selectedUnit because that is controlled by the active turn.
	int _giftSelectedBattleUnitId = -1;
	std::unordered_set<long long> _seenGiftPacketIds;
	// Incoming physical gifts received while our SavedGame is swapped out
	// (viewing the peer's base, playerInsideCoopBase). Applying them then
	// would mutate the temporary peer world and be discarded on exit - the
	// soldier would vanish on both machines. Replayed once our world is back.
	std::vector<Json::Value> _pendingIncomingGifts;
  public:
	// Single-authority model: the HOST's .sav embeds the latest client-world
	// blob (see SavedGame::save/load), so loading a host save atomically
	// restores BOTH players' rosters; the client re-fetches its world from
	// the host on reconnect. To keep the embedded blob fresh, the client
	// silently pushes its progress to the host after every soldier gift.
	void pushProgressToHostSilently();
	// Fix B (Bug 1): when the client assigns/unassigns its guest soldiers to a
	// host craft via the mirror-base UI, the assignment is written only into the
	// "basehost" blob (the client's copy of the HOST world). The client's OWN
	// world blob (client_<saveID>_<host>.data) - which GeoscapeState reloads at
	// mission end - is never updated, so the guest's CoopCraft reverts to its
	// stale value (unassigned) after a battle. This durably mirrors the
	// per-guest CoopCraft/CoopCraftType into the own-world blob (and pushes it
	// to the host) so the assignment survives the mission-end reload.
	// assignments maps a guest's CoopName to {CoopCraft, CoopCraftType}.
	void syncOwnWorldGuestCraft(int coopBaseId, const std::map<std::string, std::pair<int, std::string>>& assignments);
	// Clears session gift state (pending queues, dedup ids, away-ids)
	// after a save load - stale in-memory state must never outlive the save
	// that is now the authority.
	void resetGiftSessionState();
	// COOP living quarters: a soldier TRANSFERRED to a peer's base is never
	// erased from this machine's roster (it stays tagged with getCoopBase() =
	// that base's id), so the peer has no object to count. Report the headcount
	// per peer base so the base that HOUSES a soldier is the one that pays for
	// it. Sends only when the tally actually changed; call freely.
	void sendGuestCensus(bool force = false);
};

}
