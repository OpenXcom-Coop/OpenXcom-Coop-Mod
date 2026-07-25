# One entry point for HAND testing a live 2-player co-op session.
#
#   .\tools\coop_session.ps1                      # spin up 2 instances, connect, leave running
#   .\tools\coop_session.ps1 -Mode separate       # SEPARATE economy instead of SHARED
#   .\tools\coop_session.ps1 -Send '{"cmd":"set_ending","ending":2}'
#   .\tools\coop_session.ps1 -Send '{"cmd":"ending_state"}' -Target client
#   .\tools\coop_session.ps1 -Kill
#
# Bring-up reuses the automated harness (tools/coop_test/manual_session.py), so a
# manual session is the SAME session the suites drive - it just outlives the
# script. Both instances keep their TestServer open, which is what -Send talks to.
#
# Ports are freed before spawning, so a re-run always works even if a previous
# session is still up. Only processes holding THOSE ports are stopped - an
# unrelated OpenXcom you launched by hand is left alone.
[CmdletBinding()]
param(
    [ValidateSet("shared", "separate")][string]$Mode = "shared",
    [int]$HostPort = 49100,
    [int]$ClientPort = 49101,
    [int]$CoopPort = 48400,
    # send one TestServer command to a RUNNING session instead of spawning
    [string]$Send,
    [ValidateSet("host", "client")][string]$Target = "host",
    # stop whatever is holding this session's ports
    [switch]$Kill
)
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Stop-PortOwners($ports) {
    $stopped = @()
    foreach ($p in $ports) {
        try { $conns = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction Stop }
        catch { continue }
        foreach ($c in $conns) {
            $proc = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
            if ($proc) {
                try { Stop-Process -Id $proc.Id -Force -ErrorAction Stop; $stopped += "$($proc.ProcessName)($($proc.Id))" }
                catch {}
            }
        }
    }
    return $stopped
}

# ---- send a command to a live instance ------------------------------------
if ($Send) {
    $port = if ($Target -eq "client") { $ClientPort } else { $HostPort }
    $c = New-Object System.Net.Sockets.TcpClient("127.0.0.1", $port)
    $s = $c.GetStream()
    $w = New-Object System.IO.StreamWriter($s)
    $r = New-Object System.IO.StreamReader($s)
    $w.WriteLine($Send); $w.Flush()
    $r.ReadLine()
    $c.Close()
    return
}

# ---- tear a session down ---------------------------------------------------
if ($Kill) {
    $stopped = Stop-PortOwners @($HostPort, $ClientPort, $CoopPort)
    if ($stopped) { Write-Host "stopped: $($stopped -join ', ')" } else { Write-Host "nothing listening on $HostPort/$ClientPort/$CoopPort" }
    return
}

# ---- spin up ---------------------------------------------------------------
$exe = Join-Path $root "bin\x64\Release\OpenXcom.exe"
if (-not (Test-Path $exe)) { throw "no build at $exe - run .\tools\worktree_bootstrap.ps1 -Build" }

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { throw "python not found on PATH" }

$stopped = Stop-PortOwners @($HostPort, $ClientPort, $CoopPort)
if ($stopped) {
    Write-Host "freed ports from a previous session: $($stopped -join ', ')"
    Start-Sleep -Seconds 2
}

Write-Host "== bringing up a $Mode co-op session (this takes a minute)"
& $python.Source (Join-Path $root "tools\coop_test\manual_session.py") `
    --mode $Mode --host-port $HostPort --client-port $ClientPort --coop-port $CoopPort
if ($LASTEXITCODE -ne 0) { throw "bring-up failed rc=$LASTEXITCODE" }

# Single-quoted here-string: the JSON below is full of double quotes and must
# reach the console verbatim, not through PowerShell's escape rules.
Write-Host @'

force a defeat (then click a time-speed button on the host):
  .\tools\coop_session.ps1 -Send '{"cmd":"set_ending","ending":2}'
inspect:
  .\tools\coop_session.ps1 -Send '{"cmd":"ending_state"}'
  .\tools\coop_session.ps1 -Send '{"cmd":"coop_dialog_info"}' -Target client
tear down:
  .\tools\coop_session.ps1 -Kill
'@
