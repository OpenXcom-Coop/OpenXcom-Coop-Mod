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

## B3: Duplicate bases from previous campaigns after base placement

**Symptoms:** Immediately after placing the first base in a new PvP campaign, two
bases appear on the geoscape with the same name. The duplicate disappears shortly
after or when clicked on.

**Likely cause:** Previous campaign's save data persists in `coopFilesHost` or
`coopFilesClient` after `closeLobby()` / `startCampaign()`. The `campaignStarted()`
call clears `coopFilesHost/Client` (line 740-741 of LobbyMenu.cpp), but a
previous session's base might be lingering in `_bases` or the geoscape renderer
if the game wasn't fully restarted between sessions.

**Status:** Logged, not investigated.
