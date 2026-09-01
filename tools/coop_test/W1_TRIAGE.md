# W1 triage manifest (R1-P6, commit C4)

Bucket table for every `tools/coop_test/test_*.py` file at rewrite/battlescape
HEAD (post C3 `3889d384b`), per RB-D21 (SKIP-PENDING guard mechanism) and
RB-D28 (TOOLING-PENDING marks). See
`C:\Users\bentl\openxcom-coop-agent-docs\rewrite\SPIKE-RUNBOOK.md` Section 3 for the
decisions ledger and Section 5 R1-P6 for the packet that produced this file.

## Summary

- **GREEN**: 92 (every one ran green in a full sequential pass; see report)
- **SKIP-PENDING**: 52 (4 pre-existing C2 guards + 48 new this packet)
- **TOOLING-PENDING**: 2 (not `test_*.py`; RB-D28)
- **DELETED**: 38 (32 `test_parallel_*` + 6 other #166-introduced test files; all removed by the C1 revert, none exist as files any more)
- Total `test_*.py` on disk: 144 (GREEN + SKIP-PENDING)
- Total test files that existed at cbff7951d (pre-revert): 182

Note: the packet text described the DELETED bucket as "the test_parallel_*" family; the actual accounting also found 6 more #166-introduced test files (test_battle_tripwire.py, test_coop_id_manifest.py, test_coop_outcome_gaps.py, test_coop_script_rng.py, test_shared_parallel_campaign.py, test_sync_check.py) gone for the identical reason (absent at a7106c882, present at cbff7951d, removed by the C1 revert of cbff7951d) - listed below for a complete manifest.

## GREEN

Ran in a full sequential pass with the machine-wide harness lock; every one green.

| test | reason |
|---|---|
| `test_bug_fixes.py` | gift bugs: soldier-list race, gift dialog palette, owner resolution (no battle) |
| `test_client_zero_disk.py` | client-zero-disk save-authority guarantee |
| `test_coop_base_equip_visibility.py` | issue #33 base-inventory ground-pane leak (base screen only) |
| `test_coop_guest_craft_seat.py` | guest craft seat persistence (base/craft, no battle) |
| `test_coop_quarters_accounting.py` | base quarters accounting |
| `test_coop_transfer_equipment_counts.py` | transfer equipment count conservation (base) |
| `test_coop_transfer_equipment_option.py` | transfer equipment option toggle (base) |
| `test_coop_transferred_equipment.py` | vanilla-transfer equipment conservation (base, no mission launch) |
| `test_craft_status_sync.py` | craft geoscape status string sync |
| `test_crash_produces_dump.py` | crash dump production (process-level, no battle) |
| `test_crashlog_modlist.py` | crashlog modlist capture |
| `test_geoscape_sync.py` | geoscape sync |
| `test_gift_fresh.py` | soldier gift (fresh session, base/geoscape) |
| `test_gift_rollback.py` | soldier gift rollback (base/geoscape) |
| `test_host_save_client_craft_out.py` | host-save craft-out edge case |
| `test_hotseat_start.py` | hotseat launch from New Battle screen; single-machine, no coop wire (SP-normal battle launch) |
| `test_lobby_dialogs.py` | lobby dialogs |
| `test_lobby_gating.py` | lobby gating |
| `test_lobby_polish.py` | lobby polish |
| `test_new_campaign_flow.py` | new campaign flow |
| `test_purchase_sync_repro.py` | purchase sync |
| `test_reconnect_dialog.py` | reconnect dialog (geoscape drop) |
| `test_rejoin_flow.py` | rejoin flow (geoscape) |
| `test_resume_flow.py` | campaign resume flow (F3), no battle |
| `test_save_upgrade.py` | save upgrader detector/runner, raw YAML, no SavedGame/battle built |
| `test_save_upgrade_flow.py` | save upgrader load-gate + real campaign resume flow, no battle |
| `test_server_browser.py` | server browser |
| `test_session_hardening.py` | session hardening |
| `test_shared_alert_hazards.py` | SHARED alert hazards |
| `test_shared_alerts.py` | SHARED alerts |
| `test_shared_arrival_owner_labels.py` | SHARED arrival owner-prefixed labels |
| `test_shared_base_attack.py` | SHARED base-attack alert/broadcast (turret sequence is host-only, no client battle) |
| `test_shared_basescape_restream_crash.py` | issue #124 BasescapeState double-free after world restream (base screen) |
| `test_shared_bootstrap.py` | SHARED bootstrap |
| `test_shared_capacity_host_gate.py` | SHARED craft/armor capacity host re-validation |
| `test_shared_checksum.py` | SHARED world checksum coverage (GAP-4) |
| `test_shared_commerce.py` | SHARED commerce |
| `test_shared_craft.py` | SHARED craft command/interception/dogfight routing |
| `test_shared_craft_capacity.py` | SHARED craft capacity |
| `test_shared_craft_soldiers_visibility.py` | SHARED craft soldiers visibility |
| `test_shared_deploy.py` | SHARED pre-battle squad assembly (craft assignment only, no mission launch) |
| `test_shared_disconnect.py` | SHARED disconnect handling |
| `test_shared_dogfight_button_desync.py` | SHARED dogfight button desync (craft interception, not battlescape) |
| `test_shared_dogfight_concurrent.py` | SHARED concurrent dogfights |
| `test_shared_dogfight_control.py` | SHARED dogfight control handoff |
| `test_shared_dogfight_dest.py` | SHARED dogfight destination sync |
| `test_shared_dogfight_highlight.py` | SHARED dogfight highlight |
| `test_shared_dogfight_present.py` | SHARED dogfight presentation |
| `test_shared_dogfight_sfx.py` | SHARED dogfight SFX replication (craft interception, not battlescape) |
| `test_shared_dogfight_shared.py` | SHARED dogfight shared-craft handling |
| `test_shared_dogfight_xp.py` | SHARED dogfight XP award |
| `test_shared_equip.py` | SHARED equip screens |
| `test_shared_equip2.py` | SHARED equip screens (2) |
| `test_shared_equip_transfer.py` | SHARED equip transfer |
| `test_shared_facilities.py` | SHARED facilities |
| `test_shared_facility_refresh.py` | SHARED facility refresh |
| `test_shared_flag.py` | PRD-J01 SHARED/SEPARATE campaign-type flag (no SHARED behavior/battle exercised) |
| `test_shared_gift.py` | SHARED soldier gift (geoscape/base) |
| `test_shared_graphs.py` | SHARED graphs |
| `test_shared_hk_dogfight.py` | SHARED hunter-killer dogfight |
| `test_shared_ingame_coop_menu.py` | SHARED in-game coop menu |
| `test_shared_intercept_spectate.py` | PRD-DF01 SHARED interception spectate (dogfight, not battlescape) |
| `test_shared_lobby_details.py` | SHARED lobby details |
| `test_shared_manufacture.py` | SHARED manufacture |
| `test_shared_missile_bombardment.py` | SHARED missile bombardment: explicitly the base-attack outcome with NO battlescape |
| `test_shared_newbase.py` | SHARED new base |
| `test_shared_production_sell.py` | SHARED production sell |
| `test_shared_purchase.py` | SHARED purchase |
| `test_shared_recruit_stores_full.py` | SHARED recruit-blocked-by-full-stores |
| `test_shared_refresh.py` | SHARED refresh |
| `test_shared_reload_hold.py` | SHARED reload hold |
| `test_shared_research.py` | SHARED research |
| `test_shared_research_refresh.py` | SHARED research refresh (flaked once under batch load, timed out waiting for client lobby; reran clean in isolation - not reproducible, see report) |
| `test_shared_resume.py` | SHARED resume (geoscape, not mid-battle) |
| `test_shared_resync.py` | PRD-J10 desync auto-repair (geoscape world checksum) |
| `test_shared_resync_storm.py` | issue #91 resume-hold strand (geoscape restream) |
| `test_shared_sim.py` | PRD-J04 host simulation authority (geoscape) |
| `test_shared_site_expiry.py` | issue #78 SHARED terror-site lifecycle (geoscape) |
| `test_shared_site_types.py` | issue #78 site type/field parity sweep (geoscape) |
| `test_shared_soldier_arrival_crash.py` | issue null-base BasescapeState crash on soldier arrival (base screen) |
| `test_shared_soldier_ownership.py` | SHARED bootstrap owner split (roster only, not battle control) |
| `test_shared_soldier_rename.py` | SHARED soldier rename |
| `test_shared_soldier_views_visibility.py` | SHARED soldier views visibility |
| `test_shared_soldier_visibility.py` | SHARED soldier visibility |
| `test_shared_ufo_alert.py` | SHARED UFO alert (geoscape) |
| `test_shared_waypoint_arrival.py` | SHARED waypoint arrival (geoscape) |
| `test_shared_waypoint_retarget.py` | SHARED waypoint retarget (geoscape) |
| `test_shared_world_equal.py` | SHARED world-equality control |
| `test_udp_bringup.py` | UDP transport bring-up |
| `test_udp_purchase.py` | UDP transport purchase |
| `test_ufo_notice.py` | UFO notice alert (geoscape) |
| `test_vote_system.py` | host-authoritative VoteMenu (production votes + session) |

## SKIP-PENDING

Each file carries a 2-line header guard (RB-D21): `# RW-TRIAGE: SKIP-PENDING(<unlock phase>)` then `print("SKIP-PENDING: rewrite"); sys.exit(0)`, placed after stdlib imports and before any `sys.path.insert` / `from harness import` / other module import, so the file is genuinely inert (never touches a deleted symbol or module). All 49 guarded files were individually executed this packet and confirmed to print `SKIP-PENDING: rewrite` and exit 0.

| test | unlock phase | reason |
|---|---|---|
| `test_coop_debrief_sync.py` | r4 T2 | C2 keeper guard, verified correct (killedBy/murdererId debrief parity needs battle+debrief machinery) |
| `test_coop_wait_banner.py` | R3-P1 | RELABELED this packet from SKIP-PENDING(R2-P6): R2-P6 built the STR table + `_txtCoopWait` widget + `CoopBattleUi` deny/cancel presenter, but this test's 5 scenarios drive the OLD P5 busy-owner banner (`getPrimaryBusyActor()`/`isBusy()` owner-latch, TestServer `parallel()` `coopWaitBanner` field, `STR_COOP_WAIT_FOR_PLAYER_ACTION`) which ADDENDUM (f) explicitly kills as dead driving logic, not the new deny/cancel presenter this packet built; needs the R3-P1 client `bt_deny` wiring (and likely a scenario rewrite against the new admission model) before it can run |
| `test_skirmish_end_main_menu.py` | r4 T6 | C2 keeper guard, verified correct (skirmish debrief/teardown routing) |
| `test_crash_reporter.py` | R2-P9 | RELABELED this packet from SKIP-PENDING(G1) [wrong - cannot run at G1] to SKIP-PENDING(R2-P9): needs the crash-bundle/CoopCrashPromptState machinery RB-D20 rebuilds in SharedEcon.cpp at R2-P9 |
| `test_battlescape_exit_palette.py` | R4-P2 | mid-battle co-op save load + exit teardown (battle bring-up + resume) |
| `test_battlescape_soldier_gift.py` | r3 | live in-battle soldier gift during active turns (battle-action e2e); shares mid-battle-resume setup |
| `test_campaign_then_skirmish_debrief.py` | r5/W6 | drives a full PvP skirmish battle (gamemode 2) to debrief; groups with the PvP battle suite |
| `test_coop_alien_launcher_item_loss.py` | r3 | issue #74 item-id lockstep after replicated shot (item/inventory-in-battle atom) |
| `test_coop_basedef_temp_ufo_uaf.py` | R4-P2 | base-defense temp_ufo UAF (explicit per packet) |
| `test_coop_blast_item_damage.py` | r3 | issue #74 symmetric blast item destruction (explosions atom) |
| `test_coop_door_sync.py` | r3 | issue #143 UFO door-open sync via UnitTurnBState (battle-action e2e) |
| `test_coop_double_turn_tu.py` | r3 | double-TU-on-turn regression, directly overlaps the spike's own turn atom (battle-action e2e) |
| `test_coop_inventory_item_theft.py` | r3 | issue #74 full chain: item fabrication + hand desync (item/inventory-in-battle atom) |
| `test_coop_peer_equip_screens.py` | r4/r5 | RECLASSIFIED from GREEN (ran, FAILED): drives base-screen inventory_move, which TestServer.cpp:6468 stubs to {"error":"rewrite-pending"} since R1-P4 (comment: InventoryState::getInventoryForTest()/Inventory::harnessMoveItem() removed by the r1 vanilla restore, dead until r4/r5 rebuild an equivalent hook) - not a genuine base/economy regression |
| `test_coop_proximity_item_sweep.py` | r3 | proximity-grenade floor-sweep regression (explosions/proximity atom) |
| `test_coop_pvp_blaster.py` | r3 | issue #74 in PvP alien-seat context (item atom, PvP is just the repro context) |
| `test_coop_resume_battle_control.py` | R4-P2 | mid-battle RESUME must restore split control, SEPARATE mode (battle resume) |
| `test_coop_ufo_door_close.py` | r3 | UFO door-close sync at end-turn (battle-action e2e) |
| `test_cydonia_coop_start.py` | R4-P2 | Cydonia mission start sync (explicit per packet) |
| `test_pvp_campaign_battle.py` | fast-follow | test_pvp_campaign_* family, owner descope Section 1.1 |
| `test_pvp_campaign_bringup.py` | fast-follow | test_pvp_campaign_* family, owner descope Section 1.1 |
| `test_pvp_campaign_geoscape.py` | fast-follow | test_pvp_campaign_* family, owner descope Section 1.1 |
| `test_pvp_campaign_month.py` | fast-follow | test_pvp_campaign_* family, owner descope Section 1.1 |
| `test_pvp_campaign_reconnect.py` | fast-follow | test_pvp_campaign_* family, owner descope Section 1.1 |
| `test_pvp_campaign_resume.py` | fast-follow | test_pvp_campaign_* family, owner descope Section 1.1 |
| `test_pvp_campaign_ufo_spawn.py` | fast-follow | test_pvp_campaign_* family, owner descope Section 1.1 |
| `test_pvp_dogfight.py` | r5/W6 | issue #151 test_pvp_* battle suite |
| `test_pvp_duplicate_bases.py` | r5/W6 | issue #151 test_pvp_* battle suite |
| `test_pvp_skirmish_abort.py` | r5/W6 | issue #151 test_pvp_* battle suite |
| `test_pvp_skirmish_census.py` | r5/W6 | issue #151 test_pvp_* battle suite |
| `test_pvp_skirmish_end_turn.py` | r5/W6 | issue #151 test_pvp_* battle suite |
| `test_pvp_skirmish_gamemode_selection.py` | r5/W6 | issue #151 test_pvp_* battle suite |
| `test_pvp_skirmish_psi.py` | r5/W6 | issue #151 test_pvp_* battle suite |
| `test_pvp_skirmish_rejoin.py` | r5/W6 | issue #151 test_pvp_* battle suite |
| `test_pvp_skirmish_turn_control.py` | r5/W6 | issue #151 test_pvp_* battle suite |
| `test_pvp_skirmish_win_lose.py` | r5/W6 | issue #151 test_pvp_* battle suite |
| `test_resume_game_in_battle.py` | R4-P2 | issue #93 mid-battle drop + RESUME GAME (battle resume/entry) |
| `test_shared_autoend_crashsite.py` | R4-P2 | empty-battle auto-end heap corruption; needs battle bring-up/mission-start machinery |
| `test_shared_base_defense.py` | R5 | PRD-J09 GAP-1 base-defense ownership control split (deploys real BattleUnits, faction/gating) |
| `test_shared_battle.py` | R4-P1 | PRD-J09 AC2/AC3 SHARED squad battle bring-up + post-battle merge (battle handshake/entry) |
| `test_shared_battle_turn_control.py` | R4-P1 | SHARED coop turn-init handshake + isSelectable split (battle handshake/entry) |
| `test_shared_landing.py` | R4-P1 | RECLASSIFIED from GREEN (ran, TIMEOUT): steps 1-4 (pure UX routing) pass cleanly every time; step 5 CONFIRM drives a real battle entry (waits on battle_state.inBattle on both machines) and hangs forever - groups with test_shared_battle.py's battle handshake/entry bucket |
| `test_shared_month_run.py` | r3 | SHARED long-run playthrough with an embedded mixed-owner squad battle (battle-action e2e) |
| `test_shared_resume_battle_control.py` | R4-P2 | mid-battle RESUME must restore split control, SHARED mode (battle resume) |
| `test_shared_soldier_gift_dup.py` | R5 | issue #126 in-battle gift + SHARED ownership post-battle restream (faction/gating) |
| `test_shared_soldier_ownership_battle.py` | R5 | bootstrap owner split reaching in-battle control (faction/gating) |
| `test_skirmish_battle_turn_control.py` | R4-P1 | skirmish coop turn-init handshake (battle handshake/entry) |
| `test_skirmish_debrief_disconnect.py` | r4 T6 | skirmish debrief disconnect routing; sibling of test_skirmish_end_main_menu (r4 T6) |
| `test_skirmish_flow.py` | R4-P1 | skirmish lobby flow whose step 7 ends inside BattlescapeState (battle handshake/entry) |
| `test_skirmish_rejoin_battle.py` | r4 T5 | issue #93 rejoin a running skirmish battle; battle_leave/rejoin reserved for r4 T5 per Section 2.1 |
| `test_unload_weapon_crash.py` | r4/r5 | RECLASSIFIED from GREEN (would have FAILED): drives inventory_unload, stubbed identically to inventory_move at TestServer.cpp:6480 since R1-P4, same r4/r5 rebuild note |
| `test_vote_abort_battle.py` | r3 | ABANDON MISSION vote inside a live battle (battle-action e2e) |

## TOOLING-PENDING (RB-D28)

Not `test_*.py` (harness driver scripts); checked out in C2, not runnable in the spike.

| file | unlock | reason |
|---|---|---|
| `tools/coop_test/run_matrix.py` | W6 | drives deleted test_parallel_soak; RB-D28 |
| `tools/coop_test/run_parallel.py` | W6 | drives deleted test_parallel_soak; RB-D28 |

## DELETED

Removed by the C1 revert (`git revert --no-edit cbff7951d`); none exist as files in this worktree.

### `test_parallel_*` family (32 files)

- `test_parallel_alien_death_decouple.py`
- `test_parallel_atomic_death.py`
- `test_parallel_boundary_barrier.py`
- `test_parallel_chain_order.py`
- `test_parallel_corpse_mint.py`
- `test_parallel_death_ghost.py`
- `test_parallel_endturn.py`
- `test_parallel_explosion_cluster.py`
- `test_parallel_explosion_thin.py`
- `test_parallel_explosive_carrier.py`
- `test_parallel_floor_drain.py`
- `test_parallel_floor_gravity.py`
- `test_parallel_heavy_death_repro.py`
- `test_parallel_intents.py`
- `test_parallel_introspection.py`
- `test_parallel_loose_death.py`
- `test_parallel_no_reroll.py`
- `test_parallel_objective_leak.py`
- `test_parallel_pacing_escape.py`
- `test_parallel_peer_liveness.py`
- `test_parallel_persist_alarm.py`
- `test_parallel_replay_decouple.py`
- `test_parallel_resume.py`
- `test_parallel_rx_order.py`
- `test_parallel_sharedturn.py`
- `test_parallel_skip.py`
- `test_parallel_soak.py`
- `test_parallel_speed_skew.py`
- `test_parallel_state_watermark.py`
- `test_parallel_terrain_pacing.py`
- `test_parallel_turn_skew.py`
- `test_parallel_xp_module.py`

### Other #166-introduced test files (6 files)

| file | reason |
|---|---|
| `test_battle_tripwire.py` | battle-tripwire desync detector helper (#166-introduced) |
| `test_coop_id_manifest.py` | id-manifest test (#166-introduced) |
| `test_coop_outcome_gaps.py` | outcome-gap coverage (#166-introduced) |
| `test_coop_script_rng.py` | script-RNG determinism test (#166-introduced) |
| `test_shared_parallel_campaign.py` | SHARED parallel-campaign test (#166-introduced) |
| `test_sync_check.py` | sync-check tool test (#166-introduced) |

## Reclassifications made this packet

Three files were originally bucketed GREEN by content/docstring triage, ran, and were reclassified SKIP-PENDING after root-causing the failure (per the packet's own reclassification rule: needs r2+/battle machinery, not a genuine regression):

- **`test_coop_peer_equip_screens.py`** -> `r4/r5`. Drives base-screen `inventory_move`; `src/CoopMod/TestServer.cpp:6468` stubs that command to `{"error":"rewrite-pending"}` since R1-P4, with an explicit code comment that `InventoryState::getInventoryForTest()`/`Inventory::harnessMoveItem()` were removed by the r1 vanilla restore and are "dead until r4/r5 rebuild an equivalent hook".
- **`test_unload_weapon_crash.py`** -> `r4/r5`. Drives `inventory_unload`, stubbed identically at `TestServer.cpp:6480` for the same reason.
- **`test_shared_landing.py`** -> `R4-P1`. Steps 1-4 (pure UX landing-broker routing) pass cleanly and repeatably; step 5 (CONFIRM) drives a real battle entry (`battle_state.inBattle` wait, both machines) and hangs forever - groups with `test_shared_battle.py`'s battle handshake/entry bucket.

`test_crash_reporter.py`'s pre-existing C2 guard was also relabeled from `SKIP-PENDING(G1)` (wrong - it cannot run at G1) to `SKIP-PENDING(R2-P9)` per this packet's explicit instruction (needs the crash-bundle/CoopCrashPromptState machinery RB-D20 rebuilds in SharedEcon.cpp).

## Flakes observed (not reclassified, not a regression)

Two different GREEN-bucket tests each failed in exactly one of the three full sequential runs made this packet, and passed cleanly every other time including immediate isolated re-runs:

- `test_shared_research_refresh.py` - timed out waiting for the client LobbyMenu during bring-up in the first (95-test) run; passed in the second full run and in an isolated re-run.
- `test_shared_arrival_owner_labels.py` - timed out waiting for `ItemsArrivingState` in the second (92-test) run; passed in the first full run and in an isolated re-run.
Both are `wait_for(..., timeout=...)` races against a hire/arrival or lobby event under sequential harness load (same class as the pre-existing "harness clock race" pattern behind the old test_shared_manufacture flake) and are unrelated to each other or to any r1 code change - each test's own logic is sound and its failure is not reproducible on retry.

