# Known PvP Bugs

Found while manually testing PvP campaign flows. Not yet reproduced in automated tests.

## B1: No alien events spawned when host is alien (gamemode 3)

**Symptoms:** When the host plays aliens (gamemode 3), the geoscape spawns no alien
activity — no flying UFOs, landed UFOs, terror missions, or alien bases. The XCOM
player has nothing to intercept or fight.

**Likely cause:** Alien mission generation is gated on the XCOM-side player's base
radar detection or on `GeoscapeState` time advancement. In PvP with host=alien,
the host (alien side) may not be advancing the simulation clock, or alien
missions require a human presence (`FACTION_PLAYER` bases) that the alien host
lacks.

**Status:** Logged, not investigated.

## B2: No end-of-month report when host is alien (gamemode 3)

**Symptoms:** Month-end rolls without showing the monthly financial/summary report
to the XCOM player.

**Likely cause:** The end-of-month report is triggered by `GeoscapeState::think()`
when time reaches month-end. In gamemode 3, the host is the alien side and may
not be advancing time properly, or the monthly report popup is gated on a
condition the alien host doesn't satisfy.

**Status:** Logged, not investigated.

## B3: "Duplicate bases from a previous campaign" — MIS-DIAGNOSED (no cross-campaign leak)

**Original report:** starting a second PvP campaign in the same process supposedly
leaves a stale base from the first campaign on the geoscape as a duplicate.

**Reality:** the engine does NOT leak bases across campaigns. Two things made the
original repro look like a bug:

1. **Mis-wired teardown.** The old repro's `abort_to_main_menu` drove
   `dismiss_popup` to get back to the main menu between campaigns. On a bare
   `GeoscapeState` there is no `CoopState` to pop, so `dismiss_popup` is a no-op
   (TestServer.cpp) — the process never returned to the menu, and the run
   *errored* on the `MainMenuState` wait instead of testing anything.
2. **coopIcon-blind classifier.** The old "real base" filter keyed only on
   `coopBase`, so a `_coopIcon` mirror (which has `coopBase==false`) was
   miscounted as a real base. The engine's own predicate is
   `coopBase==false AND coopIcon==false` (TestServer.cpp).

**Why no leak is possible:** campaign 2's `newgame_ok` calls
`Game::setSavedGame(save)`, which `delete`s the previous `SavedGame` and its
entire base list — real bases *and* any `_coopIcon` mirror. `startCampaign()`
also mints a fresh `saveID` and clears both `coopFilesHost`/`coopFilesClient`
(LobbyMenu.cpp), and the world blobs are `saveID`-keyed, so a stale blob cannot
be re-applied under the new campaign either. `resetSession()` (run on the
abandon-to-menu path) additionally resets `saveID` to 0 and empties the blob
maps.

**Repro is now a hard assertion:** `tools/coop_test/test_pvp_duplicate_bases.py`
tears down between campaigns with the real `disconnect_to_menu` command
(disconnectTCP + `setServerOwner(false)` + `resetSession` + `GoToMainMenuState`)
and *proves* the process is pristine (MainMenuState up, `hasSave==false`,
`saveID==0`) before campaign 2. It then asserts, after each campaign's XCOM-side
placement, exactly one real base (`coopBase==false AND coopIcon==false`) named
`XcomBase` at the placed coordinates, zero `_coopIcon` mirrors named `XcomBase`,
and one real base total. It **passes** for both gm2 (client=alien) and gm3
(host=alien): each campaign shows a fresh `XcomBase` (its `coopBaseId` changes
every campaign), with no carry-over.

**Status:** RESOLVED as a repro/classifier defect — no engine change was needed
for the cross-campaign story.

### Still open (separate, in-scope for a future fix): within-campaign `_coopIcon` self-mirror

A genuinely-visible *within-campaign* duplicate exists and is NOT this bug: a
SEPARATE-mode `_coopIcon` mirror base minted by the `coopBase`-family handlers can
collide with a real base of the same name on the same machine. That is a distinct,
still-open defect; the cross-campaign repro above does not exercise or fix it.

### Optional engine hardening (deferred)

The coop mirror statics `playersBases` / `playersFunds` (lobby detail text) and
`j_markers` / `onceTime` (marker sync) are reset only by the sync handshake, not
by `resetSession()`. Clearing them in `resetSession()` (and calling
`resetSession()` from the coop branch of `NewGameState::btnOkClick` before
`lobbyMode=1`) would make the same-process new-campaign path pristine without a
menu visit. This is pure belt-and-suspenders — there is no failing case, since
these statics are display/marker state, not base-list state, and the assertion
repro is already green without it — so it was deferred rather than adding rebuild
risk to marker-sync statics on an already-clean teardown path.
