# Runs the coop suite on THIS machine the way CI runs it, with CI's N shard machines replaced
# by N harness slots of one machine: the same planner (plan_shards.ps1, unchanged), the same
# runner (run_coop_suite.ps1: one test at a time, one attempt, slow_test_exceptions.json
# budgets and hard-kill), the same test set (boot_check + every tools/coop_test/test_*.py) and
# CI's timings merge (merge_timings.ps1, as the coop-tests job runs it). The shards run AT THE
# SAME TIME: shard k (1..N) runs on harness slot SlotBase + k - 1 (OXC_HARNESS_SLOT), with the
# SDL dummy drivers the CI step sets. Windows (Windows PowerShell 5.1 or pwsh 7).
#
#   ./tools/ci/run_local_suite.ps1 -Out <new or empty dir>                   # the whole suite, 4 shards, slots 0-3
#   ./tools/ci/run_local_suite.ps1 -Out <dir> -ListOnly                      # print the plan and the test count, run nothing
#   ./tools/ci/run_local_suite.ps1 -Out <dir> -Only test_a,test_b            # just these tests, planned the same way
#   ./tools/ci/run_local_suite.ps1 -Out <dir> -Shards 2 -SlotBase 4 -Timings <json>
#
# -Timings is the planner's measured-times input, laid over tools/ci/test_weights.json (CI: the
# restored timings cache). Default: the newest timings-merged.json in a sibling directory of -Out,
# else none, so plan_shards.ps1 uses tools/ci/test_weights.json alone exactly as CI does on a cold cache. The merge uses the same file as
# its previous value (CI: -Prev .ci_timings/timings.json). An -Only run's timings-merged.json holds
# only its own tests plus that previous value, so keep -Only runs out of a full run's parent dir
# (or pass -Timings).
# -Only plans just the named tests with plan_shards.ps1 (unchanged) over a stub tree holding only
# them (boot_check weighs 0 there when it is not named, then leaves the plan); every other test
# goes to a "not-run" plan entry so run_coop_suite.ps1's stale-plan check still passes.
#
# <Out>: shard-plan.json, timings-<k>.json, timings-merged.json, logs\shard<k>\<test>.log,
# shard<k>.console.log + shard<k>.stderr.log, crash\ (copies of new crash files) and SUMMARY.md.
# Refused before anything runs (exit 4): -Out not empty, a shard slot reaching 50
# (test_crash_attribution's second game uses slot + 50), an -Only name that is no CI test,
# an exe older than the newest src file, bin\common / bin\standard not staged next to the exe,
# or a used slot's harness lock held. Exit 0 = every shard exit 0; 1 = any shard non-zero.
param(
  [Parameter(Mandatory)][string]$Out,
  [int]$Shards = 4,
  [int]$SlotBase = 0,
  [string]$Timings,
  [string[]]$Only,
  [switch]$ListOnly
)
$ErrorActionPreference = "Stop"

$repo    = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$testDir = Join-Path $repo "tools\coop_test"
$planner = Join-Path $PSScriptRoot "plan_shards.ps1"
$suite   = Join-Path $PSScriptRoot "run_coop_suite.ps1"
$merger  = Join-Path $PSScriptRoot "merge_timings.ps1"
$python  = if ($env:OS -eq "Windows_NT") { "python" } else { "python3" }
$hostExe = (Get-Process -Id $PID).Path            # the same PowerShell runs the shards
# The exe the harness drives (harness.py EXE): OXC_TEST_EXE, else bin\x64\Release\OpenXcom.exe.
$exe     = if ($env:OXC_TEST_EXE) { $env:OXC_TEST_EXE } else { Join-Path $repo "bin\x64\Release\OpenXcom.exe" }
$exe     = [System.IO.Path]::GetFullPath($exe)
$exeDir  = Split-Path -Parent $exe
$Out     = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Out)
$started = Get-Date

function Write-Summary([string[]]$lines) {
  [System.IO.File]::WriteAllText((Join-Path $Out "SUMMARY.md"), (($lines -join "`n") + "`n"), (New-Object System.Text.UTF8Encoding($false)))
}

function Refuse([string[]]$why, [bool]$writeSummary) {
  foreach ($w in $why) { Write-Host "REFUSED: $w" }
  if ($writeSummary) { Write-Summary (@("# LOCAL SUITE SUMMARY", "VERDICT: REFUSED") + @($why | ForEach-Object { "- $_" })) }
  exit 4
}

# --- Arguments --------------------------------------------------------------------
if (Test-Path -LiteralPath $Out) {
  if (-not (Test-Path -LiteralPath $Out -PathType Container) -or (Get-ChildItem -LiteralPath $Out -Force | Select-Object -First 1)) {
    Refuse @("out dir $Out exists and is not empty") $false
  }
}
if ($Shards -lt 1)   { Refuse @("-Shards $Shards`: give 1 or more") $false }
if ($SlotBase -lt 0) { Refuse @("-SlotBase $SlotBase`: give 0 or more") $false }
$slots = @(0..($Shards - 1) | ForEach-Object { $SlotBase + $_ })
if ($slots[-1] -ge 50) {
  Refuse @("slots $($slots -join ',') reach slot 50: test_crash_attribution runs its second game on slot + 50; keep every shard slot below 50") $false
}

# Same discovery as plan_shards.ps1 and run_coop_suite.ps1.
$tests = @(Get-ChildItem (Join-Path $testDir "boot_check.py"), (Join-Path $testDir "test_*.py") |
           Select-Object -ExpandProperty BaseName | Sort-Object)
$onlyNames = @()
if ($Only) {   # -File passes "a,b" as one string: split on commas and blanks
  $onlyNames = @($Only | ForEach-Object { $_ -split '[,\s]+' } | Where-Object { $_ } |
                 ForEach-Object { $_ -replace '\.py$', '' } | Sort-Object -Unique)
  $unknownOnly = @($onlyNames | Where-Object { $tests -notcontains $_ })
  if ($unknownOnly.Count) { Refuse @("-Only names no CI test (boot_check or tools/coop_test/test_*.py): $($unknownOnly -join ', ')") $false }
}

$timingsFrom = "given (-Timings)"
if (-not $PSBoundParameters.ContainsKey("Timings")) {
  $parent = Split-Path -Parent $Out
  $prev = @(Get-ChildItem -LiteralPath $parent -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -ne $Out } |
            ForEach-Object { Get-Item -LiteralPath (Join-Path $_.FullName "timings-merged.json") -ErrorAction SilentlyContinue } |
            Where-Object { $_ } | Sort-Object LastWriteTime -Descending)
  if ($prev.Count) { $Timings = $prev[0].FullName; $timingsFrom = "newest sibling timings-merged.json" }
  else             { $Timings = ""; $timingsFrom = "none: plan_shards.ps1 falls back to tools/ci/test_weights.json" }
} elseif ($Timings) {
  $Timings = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Timings)
}
$timingsUsable = [bool]($Timings -and (Test-Path -LiteralPath $Timings))

New-Item -ItemType Directory -Force $Out | Out-Null

# --- Plan (plan_shards.ps1, unchanged) ------------------------------------------------
function Invoke-Planner([string]$root, [string]$timingsArg, [string]$outFile) {
  Push-Location $root
  try {
    if ($timingsArg) { & $planner -Of $Shards -Timings $timingsArg -Out $outFile }
    else             { & $planner -Of $Shards -Out $outFile }
  } finally { Pop-Location }
}

$planFile = Join-Path $Out "shard-plan.json"
Write-Host "timings input: $(if ($Timings) { $Timings } else { '-' }) ($timingsFrom)"
if (-not $onlyNames.Count) {
  Invoke-Planner $repo $Timings $planFile
} else {
  $stub = Join-Path $Out "only-plan"
  New-Item -ItemType Directory -Force (Join-Path $stub "tools\coop_test"), (Join-Path $stub "tools\ci") | Out-Null
  foreach ($n in (@($onlyNames) + @("boot_check") | Sort-Object -Unique)) {
    New-Item -ItemType File -Force (Join-Path $stub "tools\coop_test\$n.py") | Out-Null
  }
  # The weights the planner would read in the repo: test_weights.json with the -Timings file (if it
  # exists) on top. boot_check's 0 goes into the file the planner reads last, so it wins.
  $wRepo = Join-Path $repo "tools\ci\test_weights.json"
  $wBase = Join-Path $stub "tools\ci\test_weights.json"
  if ($timingsUsable -and (Test-Path -LiteralPath $wRepo)) { Copy-Item -LiteralPath $wRepo -Destination $wBase }
  $wSrc = if ($timingsUsable) { $Timings } else { $wRepo }
  $w = Get-Content -LiteralPath $wSrc -Raw | ConvertFrom-Json
  if ($onlyNames -notcontains "boot_check") { $w | Add-Member -NotePropertyName "boot_check" -NotePropertyValue 0.0 -Force }
  $wStub = if ($timingsUsable) { Join-Path $stub "weights.json" } else { $wBase }
  $w | ConvertTo-Json -Depth 2 | Set-Content -LiteralPath $wStub -Encoding utf8
  $stubPlan = Join-Path $stub "plan.json"
  Invoke-Planner $stub $(if ($timingsUsable) { $wStub } else { "" }) $stubPlan
  $sp = Get-Content -LiteralPath $stubPlan -Raw | ConvertFrom-Json
  $runShards = [ordered]@{}
  foreach ($k in 1..$Shards) { $runShards["$k"] = @(@($sp.shards."$k") | Where-Object { $onlyNames -contains $_ }) }
  $runShards["not-run"] = @($tests | Where-Object { $onlyNames -notcontains $_ })
  $runPlan = [ordered]@{
    of      = $Shards
    source  = "$($sp.source) (-Only stub tree; the weights of $(if ($timingsUsable) { "$wRepo + $Timings" } else { $wRepo }))"
    median  = $sp.median
    unknown = @(@($sp.unknown) | Where-Object { $onlyNames -contains $_ })
    only    = $onlyNames
    shards  = $runShards
  }
  $runPlan | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $planFile -Encoding utf8
}
$plan = Get-Content -LiteralPath $planFile -Raw | ConvertFrom-Json

$rows = @()
foreach ($k in 1..$Shards) {
  $rows += [pscustomobject]@{
    Shard = $k; Slot = $slots[$k - 1]; Tests = @(@($plan.shards."$k") | Where-Object { $_ })
    TimingsFile = Join-Path $Out "timings-$k.json"; LogDir = Join-Path $Out "logs\shard$k"
    Console = Join-Path $Out "shard$k.console.log"; StdErr = Join-Path $Out "shard$k.stderr.log"
    Proc = $null; Start = $null; End = $null; Exit = $null; Samples = (New-Object System.Collections.Generic.List[double])
  }
}
$planned = @($rows | ForEach-Object { $_.Tests })
Write-Host ("CI tests: {0} (boot_check + {1} test_*.py); this run: {2} test(s) in {3} shard(s) on slot(s) {4}" -f
            $tests.Count, ($tests.Count - 1), $planned.Count, $Shards, ($slots -join ','))
foreach ($r in $rows) { Write-Host ("  shard {0} (slot {1}): {2} test(s): {3}" -f $r.Shard, $r.Slot, $r.Tests.Count, ($r.Tests -join ' ')) }
if ($ListOnly) { exit 0 }

# --- Preflight (run_regression.py's checks) ---------------------------------------------
$pythonExe = (Get-Command $python).Source
# The harness's own lock call in a child: rc 0 = the slot is free (run_regression.py PROBE).
$probe = "import sys; sys.path.insert(0, sys.argv[1]); import harness; harness._acquire_machine_lock(timeout=0)"
function Test-SlotFree([int]$slot) {
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = $pythonExe
  $psi.Arguments = '-c "' + $probe + '" "' + $testDir + '"'
  $psi.UseShellExecute = $false
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError = $true
  $psi.EnvironmentVariables["OXC_HARNESS_SLOT"] = "$slot"
  $psi.EnvironmentVariables.Remove("OXC_TIMELOG")
  $p = [System.Diagnostics.Process]::Start($psi)
  $errTask = $p.StandardError.ReadToEndAsync()
  $null = $p.StandardOutput.ReadToEnd()
  $null = $errTask.Result
  if (-not $p.WaitForExit(60000)) { try { $p.Kill() } catch {}; return $false }
  return $p.ExitCode -eq 0
}

# bin\common and bin\standard files whose copy under the exe dir differs in size or mtime.
function Get-Unstaged {
  $bad = New-Object System.Collections.Generic.List[string]
  foreach ($sub in "common", "standard") {
    $srcRoot = Join-Path $repo "bin\$sub"
    $dstRoot = Join-Path $exeDir $sub
    $dst = @{}
    if (Test-Path -LiteralPath $dstRoot) {
      foreach ($f in Get-ChildItem -LiteralPath $dstRoot -Recurse -File -Force) { $dst[$f.FullName.Substring($dstRoot.Length)] = $f }
    }
    foreach ($f in Get-ChildItem -LiteralPath $srcRoot -Recurse -File -Force) {
      $rel = $f.FullName.Substring($srcRoot.Length)
      $d = $dst[$rel]
      if ($d -and $d.Length -eq $f.Length -and [math]::Abs(($d.LastWriteTimeUtc - $f.LastWriteTimeUtc).TotalSeconds) -lt 2.0) { continue }
      $bad.Add("bin\$sub$rel")
    }
  }
  return ,$bad
}

$reasons = @()
$exeLine = "$exe (missing)"
if (Test-Path -LiteralPath $exe) {
  $exeM = (Get-Item -LiteralPath $exe).LastWriteTime
  $newest = Get-ChildItem -LiteralPath (Join-Path $repo "src") -Recurse -File -Force | Sort-Object LastWriteTime -Descending | Select-Object -First 1
  $fresh = (-not $newest) -or ($exeM -ge $newest.LastWriteTime)
  $exeLine = "{0} (mtime {1:s}; newest src {2:s} {3}; {4})" -f $exe, $exeM, $newest.LastWriteTime,
             $newest.FullName.Substring($repo.Length + 1), $(if ($fresh) { "fresh" } else { "STALE" })
  if (-not $fresh) { $reasons += "exe STALE: $exeLine" }
} else {
  $reasons += "exe $exe does not exist"
}
$unstaged = Get-Unstaged
if ($unstaged.Count) {
  $reasons += "data not staged: $($unstaged.Count) file(s) of bin\common, bin\standard differ from $exeDir (first: $($unstaged[0]))"
}
foreach ($s in $slots) { if (-not (Test-SlotFree $s)) { $reasons += "slot $s busy (another run holds its harness lock)" } }
if ($reasons.Count) { Refuse $reasons $true }

# --- Machine CPU (run_regression.py's GetSystemTimes method) -----------------------------
$cpuOk = $env:OS -eq "Windows_NT"
if ($cpuOk -and -not ("OxcLocalSuite.Kernel32" -as [type])) {
  Add-Type -Namespace OxcLocalSuite -Name Kernel32 -MemberDefinition @'
[DllImport("kernel32.dll")] public static extern bool GetSystemTimes(out long idle, out long kernel, out long user);
'@
}
function Get-SysTimes {
  $i = 0L; $k = 0L; $u = 0L
  [void][OxcLocalSuite.Kernel32]::GetSystemTimes([ref]$i, [ref]$k, [ref]$u)
  return ,@($i, $k, $u)
}
function Get-Busy($a, $b) {   # total CPU % between two readings (kernel time includes idle time)
  $idle = $b[0] - $a[0]; $total = ($b[1] - $a[1]) + ($b[2] - $a[2])
  if ($total -le 0) { return 0.0 }
  return [math]::Round(100.0 * ($total - $idle) / $total, 1)
}

# --- Crash files in the used slots' folders (harness.CRASH_DIR = <exe dir>\crashlogs\s<slot>;
# test_crash_attribution's second game writes to slot + 50) ---------------------------
$crashSlots = @($slots) + @($slots | ForEach-Object { $_ + 50 })
function Get-CrashFiles {
  $h = @{}
  foreach ($s in $crashSlots) {
    $d = Join-Path $exeDir "crashlogs\s$s"
    if (Test-Path -LiteralPath $d) { foreach ($f in Get-ChildItem -LiteralPath $d -Recurse -File -Force) { $h[$f.FullName] = $f } }
  }
  return $h
}
$crashBefore = Get-CrashFiles

# --- Run: every shard at once ----------------------------------------------------------------
function Stop-Tree($p) { try { & taskkill /F /T /PID $p.Id > $null 2>&1 } catch {} }
$envNames = "OXC_HARNESS_SLOT", "SDL_VIDEODRIVER", "SDL_AUDIODRIVER", "OXC_TIMELOG"
$savedEnv = @{}
foreach ($n in $envNames) { $savedEnv[$n] = [Environment]::GetEnvironmentVariable($n) }
$status = "ABORTED"
try {
  try {
    $env:SDL_VIDEODRIVER = "dummy"     # the CI step's env (ci-main.yml coop-shard)
    $env:SDL_AUDIODRIVER = "dummy"
    [Environment]::SetEnvironmentVariable("OXC_TIMELOG", $null)
    foreach ($r in $rows) {
      if (-not $r.Tests.Count) { continue }
      New-Item -ItemType Directory -Force $r.LogDir | Out-Null
      $env:OXC_HARNESS_SLOT = "$($r.Slot)"
      $argLine = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -PlanFile "{1}" -Shard {2} -TimingsOut "{3}" -LogDir "{4}"' -f
                 $suite, $planFile, $r.Shard, $r.TimingsFile, $r.LogDir
      $r.Start = Get-Date
      $r.Proc = Start-Process -FilePath $hostExe -ArgumentList $argLine -WorkingDirectory $repo -NoNewWindow -PassThru `
                  -RedirectStandardOutput $r.Console -RedirectStandardError $r.StdErr
      $null = $r.Proc.Handle   # keeps ExitCode readable after the exit (Windows PowerShell)
      Write-Host ("[{0:s}] start shard {1} slot {2}: {3} test(s)" -f $r.Start, $r.Shard, $r.Slot, $r.Tests.Count)
    }
  } finally {
    foreach ($n in $envNames) { [Environment]::SetEnvironmentVariable($n, $savedEnv[$n]) }
  }
  $last = if ($cpuOk) { Get-SysTimes } else { $null }
  $lastSample = Get-Date
  while ($true) {
    $running = @($rows | Where-Object { $_.Proc -and $null -eq $_.End })
    if (-not $running.Count) { break }
    Start-Sleep -Milliseconds 500
    if ($cpuOk -and ((Get-Date) - $lastSample).TotalSeconds -ge 5) {
      $now = Get-SysTimes; $pct = Get-Busy $last $now; $last = $now; $lastSample = Get-Date
      foreach ($r in $running) { $r.Samples.Add($pct) }
    }
    foreach ($r in $running) {
      if (-not $r.Proc.HasExited) { continue }
      if ($cpuOk -and -not $r.Samples.Count) {   # a shard shorter than one sample period still gets a number
        $now = Get-SysTimes; $r.Samples.Add((Get-Busy $last $now))
      }
      $r.Proc.WaitForExit()
      $r.End = Get-Date
      $r.Exit = $r.Proc.ExitCode
      Write-Host ("[{0:s}] end   shard {1} exit {2} wall {3:N1} s" -f $r.End, $r.Shard, $r.Exit, ($r.End - $r.Start).TotalSeconds)
    }
  }
  $status = "COMPLETE"
} finally {
  foreach ($r in $rows) { if ($r.Proc -and -not $r.Proc.HasExited) { Stop-Tree $r.Proc } }
}
$ended = Get-Date

# --- Timings merge (the coop-tests job: merge_timings.ps1 -In <shard jsons> -Prev <cache>) ---
$merged = Join-Path $Out "timings-merged.json"
$mergeLine = ""
try {
  Push-Location $repo
  try {
    if ($timingsUsable) { & $merger -In $Out -Prev $Timings -Out $merged } else { & $merger -In $Out -Out $merged }
  } finally { Pop-Location }
  $mergeLine = "$merged ($(@((Get-Content -LiteralPath $merged -Raw | ConvertFrom-Json).PSObject.Properties).Count) rows; previous value: $(if ($timingsUsable) { $Timings } else { 'none' }))"
} catch {
  $mergeLine = "FAILED: $($_.Exception.Message) (CI's merge step is continue-on-error too)"
}

# --- Results: run_coop_suite.ps1's console table line per test ---------------------------
$budgetDefault = 180.0
$budgetMap = @{}
$bc = Get-Content -LiteralPath (Join-Path $testDir "slow_test_exceptions.json") -Raw | ConvertFrom-Json
if ($null -ne $bc.default_budget_s) { $budgetDefault = [double]$bc.default_budget_s }
if ($bc.exceptions) { foreach ($p in $bc.exceptions.PSObject.Properties) { $budgetMap[$p.Name] = [double]$p.Value.budget_s } }
$lineRe = '^(PASS|FAIL|KNOWN-FAIL)\s+([0-9][0-9.,]*)s  (\S+)(?: \((.*)\))?\s*$'
$results = @()
foreach ($r in $rows) {
  $seen = @{}
  if (Test-Path -LiteralPath $r.Console) {
    foreach ($ln in Get-Content -LiteralPath $r.Console) {
      if ($ln -match $lineRe -and $r.Tests -contains $Matches[3]) {
        $seen[$Matches[3]] = @($Matches[1], [double]($Matches[2] -replace ',', ''), $Matches[4])
      }
    }
  }
  foreach ($t in $r.Tests) {
    $budget = if ($budgetMap.ContainsKey($t)) { $budgetMap[$t] } else { $budgetDefault }
    $s = $seen[$t]
    $note = if ($s) { "$($s[2])" } else { "" }
    $results += [pscustomobject]@{
      Shard = $r.Shard; Test = $t; Status = $(if ($s) { $s[0] } else { "NO RESULT" }); Seconds = $(if ($s) { $s[1] } else { $null })
      Budget = $budget; Over = ($note -match 'over .*budget'); Hung = ($note -match 'HANG'); Note = $note
      Log = Join-Path $r.LogDir "$t.log"
    }
  }
}

$crashAfter = Get-CrashFiles
$newCrash = @($crashAfter.Keys | Where-Object { -not $crashBefore.ContainsKey($_) } | Sort-Object { $crashAfter[$_].LastWriteTime })
if ($newCrash.Count) {
  New-Item -ItemType Directory -Force (Join-Path $Out "crash") | Out-Null
  foreach ($p in $newCrash) { Copy-Item -LiteralPath $p -Destination (Join-Path $Out "crash") -Force }
}

# --- SUMMARY.md -----------------------------------------------------------------------------
function Fmt($v) { if ($null -eq $v) { "n/a" } else { "{0:0.0}" -f $v } }
$ran = @($rows | Where-Object { $_.Proc })
$nbad = @($ran | Where-Object { $_.Exit -ne 0 }).Count
$verdict = if ($status -ne "COMPLETE") { "ABORTED" } elseif ($nbad) { "FAIL ($nbad of $($ran.Count) shards exit != 0)" } else { "PASS" }
$tip = try { "$(& git -C $repo rev-parse HEAD) ($(if (@(& git -C $repo status --porcelain).Count) { 'dirty' } else { 'clean' }))" } catch { "unknown" }
$count = { param($st) @($results | Where-Object { $_.Status -eq $st }).Count }
$L = @("# LOCAL SUITE SUMMARY (tools/ci/run_local_suite.ps1)",
       "VERDICT: $verdict",
       "tip: $tip",
       "exe: $exeLine",
       "plan: $planFile; weights from $($plan.source); timings input $(if ($Timings) { $Timings } else { '-' }) ($timingsFrom)",
       ("mode: {0} shard(s) at once on slot(s) {1}; {2}; started {3:s}; ended {4:s}; wall {5:N1} s" -f $Shards, ($slots -join ','),
        $(if ($onlyNames.Count) { "-Only $($onlyNames.Count) test(s)" } else { "every CI test" }), $started, $ended, ($ended - $started).TotalSeconds),
       ("totals: {0} tests: {1} passed, {2} failed, {3} known-fail, {4} hung, {5} over budget, {6} no result" -f $results.Count,
        (& $count "PASS"), (& $count "FAIL"), (& $count "KNOWN-FAIL"), @($results | Where-Object { $_.Hung }).Count,
        @($results | Where-Object { $_.Over }).Count, (& $count "NO RESULT")),
       "timings: $mergeLine",
       "",
       "## Shards",
       "| shard | slot | tests | exit | start | end | wall s | cpu avg % | cpu max % | samples >50% |",
       "|---|---|---|---|---|---|---|---|---|---|")
foreach ($r in $rows) {
  $s = @($r.Samples)
  $wall = if ($r.End) { "{0:0.0}" -f ($r.End - $r.Start).TotalSeconds } else { "-" }
  $L += ("| {0} | {1} | {2} | {3} | {4} | {5} | {6} | {7} | {8} | {9} |" -f $r.Shard, $r.Slot, $r.Tests.Count,
         $(if ($r.Proc) { $r.Exit } else { "not started (0 tests)" }), $(if ($r.Start) { "{0:HH:mm:ss}" -f $r.Start } else { "-" }),
         $(if ($r.End) { "{0:HH:mm:ss}" -f $r.End } else { "-" }), $wall,
         $(if ($s.Count) { Fmt (($s | Measure-Object -Average).Average) } else { "n/a" }),
         $(if ($s.Count) { Fmt (($s | Measure-Object -Maximum).Maximum) } else { "n/a" }),
         $(if ($s.Count) { "{0}/{1}" -f @($s | Where-Object { $_ -gt 50 }).Count, $s.Count } else { "n/a" }))
}
$L += @("", "## Tests", "| shard | test | status | seconds | budget s | over budget | note |", "|---|---|---|---|---|---|---|")
foreach ($x in ($results | Sort-Object Shard, Test)) {
  $L += ("| {0} | {1} | {2} | {3} | {4} | {5} | {6} |" -f $x.Shard, $x.Test, $x.Status, (Fmt $x.Seconds), (Fmt $x.Budget),
         $(if ($x.Over) { "OVER" } else { "-" }), $(if ($x.Note) { $x.Note } else { "-" }))
}
$L += @("", "## Non-PASS tests")
$bad = @($results | Where-Object { $_.Status -ne "PASS" })
foreach ($x in $bad) {
  $L += "### shard $($x.Shard) $($x.Test) ($($x.Status)$(if ($x.Note) { ", $($x.Note)" }), $(Fmt $x.Seconds) s)"
  $L += "log: $($x.Log)"
  $L += "``````"
  $L += $(if (Test-Path -LiteralPath $x.Log) { @(Get-Content -LiteralPath $x.Log -Tail 30 -Encoding UTF8) } else { "(no log)" })
  $L += "``````"
}
if (-not $bad.Count) { $L += "none" }
foreach ($r in $rows) {
  if (-not $r.Proc -or $r.Exit -eq 0) { continue }
  $shardNo = $r.Shard
  if (@($bad | Where-Object { $_.Shard -eq $shardNo }).Count) { continue }
  $L += "### shard $($r.Shard) exit $($r.Exit) with no non-PASS test (runner error)"
  $L += "log: $($r.StdErr)"
  $L += "``````"
  $L += @(Get-Content -LiteralPath $r.StdErr -Tail 30)
  $L += "``````"
}
$L += @("", "## Crash files: $($newCrash.Count) new in crashlogs\s<slot> for slot(s) $($crashSlots -join ',')")
if ($newCrash.Count) {
  $L += @("| file | size | mtime | folder |", "|---|---|---|---|")
  foreach ($p in $newCrash) {
    $f = $crashAfter[$p]
    $L += ("| {0} | {1} | {2:s} | {3} |" -f $f.Name, $f.Length, $f.LastWriteTime, (Split-Path -Leaf (Split-Path -Parent $p)))
  }
  $L += "copies: $(Join-Path $Out 'crash')"
}
Write-Summary $L
Write-Host "VERDICT: $verdict | $(Join-Path $Out 'SUMMARY.md')"
if ($status -ne "COMPLETE" -or $nbad) { exit 1 }
exit 0
