# Changelog

User-facing release notes for OpenXcom Coop Mod. The release pipeline reads the
`## [<version>]` section matching a pushed `v<version>` tag and uses it as the
GitHub release body, so add a section here (and merge it to `main`) before you
tag a release. Nightlies use auto-generated notes and do not read this file.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Newest first.

## [Unreleased]
### Fixed
- Co-op SHARED campaigns: a soldier gifted between players during a battle no
  longer duplicates after the mission ends. Transferring a soldier back and forth
  in the battlescape used to leave a second copy of it in the shared roster once
  the mission finished; the shared world now moves the soldier by ownership alone,
  so the roster stays intact.
- Co-op SHARED campaigns: hiring soldiers, scientists, or engineers is no longer
  blocked with "not enough store space" when a base's general stores are full but
  its living quarters have room. Personnel occupy quarters, not stores, so a
  zero-store hire must not be rejected just because existing stores are at capacity.
- Hotseat mode can be started again. Enable it with the new HOTSEAT button on the
  New Battle screen, then press OK to launch — two players share one machine
  (Player 1 commands X-Com, Player 2 the aliens), passing the keyboard each turn
  with a line-of-sight blackout in between. The earlier menu redesign had buried
  the toggle inside the network host dialog with no way to actually begin a battle.
  An optional REACT FIRE toggle appears while hotseat is armed.

<!-- Template for the next release section (keep this comment ABOVE the newest
     released section: the notes extractor reads from "## [<v>]" until the next
     line starting with "## ", so a commented heading below a real section would
     leak a dangling "<!-" into the release body):
## [2.0.7] - 2026-XX-XX
### Added
- ...
### Fixed
- ...
### Changed
- ...
-->

## [2.0.6] - 2026-07-31

A maintenance release on top of 2.0.0: the Linux download is a self-contained
AppImage again, plus two co-op crash fixes and clearer soldier-arrival alerts.

### Fixed
- The Linux download is a self-contained AppImage again (as in v1.8.4) instead
  of a bare dynamically-linked binary, so it no longer needs matching system
  SDL libraries or a new-enough glibc to start. Built on an older base (glibc
  2.31) for broad distro support. Run `OpenXcoop-x86_64.AppImage` from the
  extracted folder, next to the data folders (see the bundled `HOW_TO_RUN.txt`).
- Fixed a crash at the end of the month when one of your bases came under
  attack in a co-op game.
- Fixed a crash for the second player when ordered soldiers arrived at a base
  in SHARED mode. Soldier-arrival alerts now list every incoming soldier for
  both players and label each with its owner's name.

## [2.0.0] - 2026-07-28

The first official release since v1.8.4, and the biggest update the mod has
had: a brand-new SHARED campaign mode, host-authoritative saving, an automatic
save upgrader, in-game voting, and a long list of desync, crash and item-loss
fixes. Windows x64, Windows XP (32-bit) and Linux packages now ship together
with every release.

### Added
- **SHARED co-op campaign** — a second co-op mode where both players run one
  world together: shared bases, funds, research, manufacturing and craft.
  Either player can command any craft, fly interceptions and dogfights, and a
  battle can mix soldiers from both players in a single squad. The campaign
  type is chosen at NEW GAME (Solo / Co-op (Separate) / Co-op (Shared)).
  Includes a periodic desync checksum with automatic repair, live economy
  refresh, and a landing broker so simultaneous craft arrivals stay ordered.
- **Save upgrader** — saves from older versions (including legacy v1.8.4 co-op
  saves) are detected on load and upgraded in-game, step by step, to the
  current format; mid-battle saves are supported. Solo saves are never
  touched.
- **Host-authoritative saving** — the host's save now embeds the client's
  world, making it the single authority for both players' campaigns; clients
  resume straight from the host's copy, so there is no more guessing which
  machine has the "right" save.
- **Multiplayer voting** — in-game vote dialogs (for example, voting to abort
  a battle), with matching lobby improvements.
- **Clipboard paste** — text fields accept paste (Ctrl+V) on Windows, Linux
  and macOS.
- **Skirmish co-op lobby** — NEW BATTLE co-op is redesigned around a
  host-driven lobby with a BATTLE SETTINGS screen and a join popup shown over
  the lobby; battles in progress can be rejoined.
- **Soldier gifting and transfers** — gift soldiers to the other player
  (optionally with their gear), including a reworked in-battle gifting flow,
  and transfer soldiers between players with rollback if the receiver cannot
  take them.
- **Server browser** — the server list can aggregate multiple rendezvous
  servers.
- **Geoscape ally indicator** — your partner's craft and bases are marked on
  the globe.
- **Off-turn scanner indicators** in battle while it is not your turn.
- **Crash reporting** — crash logs are actionable and minidumps are written
  next to them.
- Text labels in the Add Server menu and a Hotseat tooltip in the Host menu.

### Changed
- The neutral side in battle is reported as "Outsiders Activity" instead of
  "Alien Activity".
- The main menu shows a readable version block (coop version plus the OXCE
  engine version), and official releases drop the channel suffix.
- Equipment stored at the other player's bases is hidden from your own
  equip screens.
- Release packaging: the Windows x64, Windows XP i686 and Linux x86_64
  packages are built, tested and published together, and every package now
  includes the co-op art, a working official-server `rendezvous.json` and
  `LICENSE.txt`.

### Fixed
- Geoscape sync no longer floods the connection: position updates ride a
  last-write-wins lane, packet queues are thread-safe, and the "TX queue
  full" / multi-second-ping stalls are gone.
- Purchases and transfers between players: fixed a use-after-free when
  transferring a craft with crew; the receiver validates the target base
  before acknowledging, so goods are no longer silently lost; restored the
  dropped transfer notification; a transfer can no longer be applied twice;
  and a client's out-craft keeps its co-op destination across a host save.
- Battlescape item sync: battles no longer lose or duplicate items across
  machines, and a proximity-grenade blast no longer sweeps every loose item
  off the other player's floor.
- Mid-battle disconnects: a peer dropping mid-battle no longer freezes the
  game (or dumps you into a lobby), the host is no longer trapped behind the
  reconnect dialog, and "Waiting for host to resume" can no longer strand a
  client forever.
- Returning to the main menu tears the co-op session down cleanly, fixing
  crashes and palette corruption after leaving a battle.
- SHARED mode: mission sites and waypoints keep a consistent lifecycle on
  both machines, and UFO/mission detection stays in parity.
- SEPARATE mode: duplicate mission ids are de-duplicated at the snapshot
  sender.
- Chryssalid zombies no longer double-spawn in co-op battles.
- The cursor no longer misbehaves during the other player's turn.
- Craft status stays in sync between players.
- Password-protected lobbies can be joined — and left — cleanly.
- Co-op menu entry points no longer crash when no save is active.
- Fixed a crash when unloading a weapon at a base.
