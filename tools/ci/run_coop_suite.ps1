# Runs the coop test suite headless (set SDL_VIDEODRIVER/SDL_AUDIODRIVER=dummy in the
# caller's env). Exits nonzero if any non-quarantined test fails. Shared by both CI
# workflows so the quarantine list and retry policy live in exactly one place.
# Per-test durations go to the console and, on CI, to the run's Summary page
# ($GITHUB_STEP_SUMMARY) as a slowest-first table.
#
# CI runs this sharded: tools/ci/plan_shards.ps1 splits the suite by measured runtime
# and each shard job passes -PlanFile/-Shard. -TimingsOut writes this shard's measured
# durations, which the coop-tests job merges back into the cache that feeds the next
# run's plan, so a new test gets a real weight after one run.
#
#   ./tools/ci/run_coop_suite.ps1                                   # whole suite
#   ./tools/ci/run_coop_suite.ps1 -PlanFile p.json -Shard 2         # one shard
#   ./tools/ci/run_coop_suite.ps1 -PlanFile p.json -Shard 2 -ListOnly
param(
  [string]$PlanFile,
  [int]$Shard,
  [string]$TimingsOut,
  [switch]$ListOnly
)
$ErrorActionPreference = "Stop"

# Use the platform's normal Python command. setup-python provides both names on CI,
# but this also keeps local macOS/Linux runs working when only python3 is installed.
$python = if ($env:OS -eq "Windows_NT") { "python" } else { "python3" }

# Ensure the harness's Python deps. test_save_upgrade{,_flow}.py parse the two-document
# save streams with PyYAML; the CI runners do not ship it. Install once, only if missing
# (a no-op on dev machines that already have it). No stderr redirect: under
# ErrorActionPreference=Stop a redirected native stderr can raise NativeCommandError; an
# unredirected ImportError traceback is harmless (only prints on the miss, before install).
& $python -c "import yaml"
if ($LASTEXITCODE -ne 0) {
  Write-Host "installing pyyaml (required by the save-upgrade tests)..."
  & $python -m pip install --quiet --disable-pip-version-check pyyaml
  if ($LASTEXITCODE -ne 0) { throw "failed to install pyyaml" }
}

# Discover the checkout's actual harness so the suite never goes stale.
# Join-Path keeps this script usable on Windows, Linux, and macOS.
$testDir = Join-Path (Get-Location) "tools/coop_test"
$bootCheck = Join-Path $testDir "boot_check.py"
$testPattern = Join-Path $testDir "test_*.py"
$tests = Get-ChildItem $bootCheck, $testPattern |
         Select-Object -ExpandProperty BaseName | Sort-Object

if ($PlanFile) {
  if (-not $Shard) { throw "-PlanFile requires -Shard" }
  $plan = Get-Content $PlanFile -Raw | ConvertFrom-Json
  $mine = @($plan.shards."$Shard")
  if (-not $mine) { throw "shard $Shard is not in $PlanFile (of=$($plan.of))" }
  # The plan comes from the same discovery on the same commit; if it does not, some
  # test belongs to no shard and would silently go untested. Fail loudly instead.
  $planned = @($plan.shards.PSObject.Properties.Value | ForEach-Object { $_ })
  $missing = @($tests | Where-Object { $planned -notcontains $_ })
  if ($missing.Count) { throw "stale shard plan; test(s) assigned to no shard: $($missing -join ', ')" }
  $tests = @($tests | Where-Object { $mine -contains $_ })
  Write-Host "shard $Shard/$($plan.of): $($tests.Count) test(s)"
}

if ($ListOnly) { $tests; exit 0 }   # to stdout, so callers can diff the shard split

# Known-broken on main (real failures, not flakes) - run but do not gate.
# Add entries here if a test regresses; remove them as they are fixed so they gate
# again. Empty = the whole suite gates (all green as of 2026-07-15).
$quarantine = @(
  "test_pvp_campaign_month",  # issue #171: month-roll geoscape assert can't drain MissionDetectedState/SaveGameState
  "test_crash_reporter"       # issue #172: marker-bundle 60s timeout, intermittent
)

# --- Per-test time budgets ------------------------------------------------------
# There is no shard wall-clock timeout any more (the CI step used to cap the whole
# shard at 25 min; removed because the suite only grows). Enforcement is per-test
# instead: a test that FINISHES over its budget fails the suite even if it passed,
# and a test still running at hard_kill_multiplier x its budget is killed (with the
# game subtree it spawned) and failed, so a hang can never wedge a shard. Budgets +
# exceptions live in tools/coop_test/slow_test_exceptions.json and are shared
# verbatim with tools/coop_test/run_parallel.py (same JSON, two parsers).
$budgetFile    = Join-Path $testDir "slow_test_exceptions.json"
$defaultBudget = 180.0
$hardKillMult  = 2.0
$maxBudget     = 900.0
$budgetMap     = @{}
if (Test-Path $budgetFile) {
  $bc = Get-Content $budgetFile -Raw | ConvertFrom-Json
  if ($null -ne $bc.default_budget_s)     { $defaultBudget = [double]$bc.default_budget_s }
  if ($null -ne $bc.hard_kill_multiplier) { $hardKillMult  = [double]$bc.hard_kill_multiplier }
  if ($null -ne $bc.max_budget_s)         { $maxBudget     = [double]$bc.max_budget_s }
  if ($bc.exceptions) {
    foreach ($p in $bc.exceptions.PSObject.Properties) {
      $b = [double]$p.Value.budget_s
      if ($b -gt $maxBudget) {
        throw "${budgetFile}: '$($p.Name)' budget ${b}s exceeds max_budget_s ${maxBudget}s (no unlimited budgets)"
      }
      $budgetMap[$p.Name] = $b
    }
  }
  Write-Host "budgets: default ${defaultBudget}s, hard-kill ${hardKillMult}x, $($budgetMap.Count) exception(s), cap ${maxBudget}s"
} else {
  Write-Host "WARNING: $budgetFile not found; every test uses the ${defaultBudget}s default budget"
}
# Resolve python to a full path so the .NET process launcher below does not depend
# on PATH search semantics.
$pythonExe = (Get-Command $python).Source

# Run one test with a hard-kill ceiling. Returns Rc / Seconds / TimedOut. The child
# inherits our stdout/stderr (UseShellExecute=$false, no redirection) so test output
# still streams into the CI log. On the ceiling we kill the whole process tree - on
# Windows via taskkill /T (the python test spawns the game exe), elsewhere best-effort.
function Invoke-BudgetedTest {
  param([string]$Exe, [string]$TestPath, [int]$HardKillMs)
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName        = $Exe
  $psi.Arguments       = '"' + $TestPath + '"'
  $psi.UseShellExecute = $false
  $sw = [System.Diagnostics.Stopwatch]::StartNew()
  $p  = [System.Diagnostics.Process]::Start($psi)
  if ($p.WaitForExit($HardKillMs)) {
    $sw.Stop()
    return [pscustomobject]@{ Rc = $p.ExitCode; Seconds = [math]::Round($sw.Elapsed.TotalSeconds, 1); TimedOut = $false }
  }
  $sw.Stop()
  if ($env:OS -eq "Windows_NT") {
    & taskkill /F /T /PID $p.Id > $null 2>&1
  } else {
    try { Stop-Process -Id $p.Id -Force -ErrorAction Stop } catch {}
  }
  try { $p.WaitForExit(15000) | Out-Null } catch {}
  return [pscustomobject]@{ Rc = 124; Seconds = [math]::Round($sw.Elapsed.TotalSeconds, 1); TimedOut = $true }
}

$results = @()
$fail = 0
foreach ($t in $tests) {
  $testPath = Join-Path $testDir "$t.py"
  $budget   = if ($budgetMap.ContainsKey($t)) { $budgetMap[$t] } else { $defaultBudget }
  $hardMs   = [int][math]::Ceiling($budget * $hardKillMult * 1000.0)

  $r = Invoke-BudgetedTest $pythonExe $testPath $hardMs
  $attempts = 1
  if ($r.Rc -ne 0 -and -not $r.TimedOut) {        # retry a real failure once (flake tolerance)
    $r = Invoke-BudgetedTest $pythonExe $testPath $hardMs   # never retry a hang - it just hangs again
    $attempts = 2
  }
  $rc         = $r.Rc            # the LAST attempt's result/duration (a retry must
  $secs       = $r.Seconds       # not inflate the weight the next plan uses)
  $timedOut   = $r.TimedOut
  $overBudget = ($rc -eq 0 -and -not $timedOut -and $secs -gt $budget)

  # Classify. Precedence: hang > real failure > over-budget > pass. Quarantine
  # downgrades any of the failure kinds to a non-gating KNOWN-FAIL.
  $reason = $null
  if ($timedOut) {
    $hardS  = [math]::Round($budget * $hardKillMult, 1)
    $reason = "BUDGET HARD-KILL: $t still running after ${hardS}s ($($hardKillMult)x its $($budget)s budget) - killed as a hung test"
    $isFail = $true
  } elseif ($rc -ne 0) {
    $isFail = $true
  } elseif ($overBudget) {
    $reason = "BUDGET EXCEEDED: $t took ${secs}s > $($budget)s budget - re-engineer the test or add a justified exception"
    $isFail = $true
  } else {
    $isFail = $false
  }

  if (-not $isFail)                 { $status = "PASS" }
  elseif ($quarantine -contains $t) { $status = "KNOWN-FAIL" }
  else                              { $status = "FAIL"; $fail++ }

  $note = @()
  if ($attempts -gt 1)          { $note += "retried" }
  if ($status -eq "KNOWN-FAIL") { $note += "quarantined" }
  if ($timedOut)                { $note += "HANG rc=124" }
  elseif ($rc -ne 0)            { $note += "rc=$rc" }
  elseif ($overBudget)          { $note += "over ${budget}s budget" }
  $suffix = if ($note) { " ($($note -join ', '))" } else { "" }
  Write-Host ("{0,-11} {1,8:N1}s  {2}{3}" -f $status, $secs, $t, $suffix)
  if ($reason -and $status -eq "FAIL") { Write-Host "::error::$reason" }

  $results += [pscustomobject]@{ Test = $t; Status = $status; Seconds = $secs; Attempts = $attempts; Rc = $rc; Budget = $budget; OverBudget = $overBudget; TimedOut = $timedOut }
}

# Feeds the next run's plan. PASSes only: a failing test bails out early and its
# duration says nothing about how long the test actually takes.
if ($TimingsOut) {
  $timings = [ordered]@{}
  foreach ($r in ($results | Where-Object { $_.Status -eq "PASS" } | Sort-Object Test)) { $timings[$r.Test] = $r.Seconds }
  $timings | ConvertTo-Json -Depth 2 | Set-Content $TimingsOut -Encoding utf8
  Write-Host "wrote $($timings.Count) timing(s) to $TimingsOut"
}

# Duration table on the Actions run Summary page, slowest first, so the tests
# dominating CI wall time are visible without opening the logs.
if ($env:GITHUB_STEP_SUMMARY) {
  $total = [math]::Round(($results | Measure-Object Seconds -Sum).Sum, 1)
  $title = if ($PlanFile) { "Coop test durations - shard $Shard (total $($total)s)" } else { "Coop test durations (total $($total)s)" }
  $md = @("## $title", "",
          "| Test | Status | Duration | Budget | Attempts |", "| --- | --- | ---: | ---: | ---: |")
  foreach ($r in ($results | Sort-Object Seconds -Descending)) {
    $md += "| $($r.Test) | $($r.Status) | $($r.Seconds)s | $($r.Budget)s | $($r.Attempts) |"
  }
  $md -join "`n" | Add-Content $env:GITHUB_STEP_SUMMARY
}

if ($fail -gt 0) { throw "$fail non-quarantined test(s) failed" }
exit 0
