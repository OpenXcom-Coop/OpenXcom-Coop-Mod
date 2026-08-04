# Asserts a release archive is shippable. Two ways it can be wrong:
#
#   1. Too much: licensed retail X-COM data rides along. UFO/ and TFTD/ are
#      whitelisted down to their multiplayer/ subdirectory, so any other entry
#      under them fails the build (stronger than the old GEODATA-only canary,
#      which only caught one directory name).
#   2. Too little: the coop art is missing (Globe's ctor loads multiplayer/base.png
#      unguarded, so a zip without it crashes the moment a player starts a new game -
#      shipped that way in nightly 8.4.13203), or one of the files that is not build
#      output and has to be placed deliberately: rendezvous.json, LICENSE.txt.
#
# Usage: ./tools/ci/assert_package.ps1 <archive.zip>
param([Parameter(Mandatory)][string]$Archive)
$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead((Resolve-Path $Archive).Path)
# Normalize separators: pwsh 7 (CI) writes '/', Windows PowerShell 5.1 writes '\'.
# Keep files only - directory entries carry no data.
try   { $names = @($zip.Entries.FullName -replace '\\', '/' | Where-Object { $_ -notmatch '/$' }) }
finally { $zip.Dispose() }

# The stock "copy your X-COM data here" README.txt used to ship inside UFO/ and TFTD/.
# Its text now lives in HOW_TO_RUN.txt at the package root, so it must not be packaged
# (issue #137). Checked before the leak scan so it gets its own clear message.
$readmes = @($names | Where-Object { $_ -match '^(UFO|TFTD)/README\.txt$' })
if ($readmes.Count) { throw "$Archive ships $($readmes -join ', ') - its install text belongs in HOW_TO_RUN.txt, not a packaged README" }

$bad = @($names | Where-Object { $_ -match '^(UFO|TFTD)/' -and $_ -notmatch '^(UFO|TFTD)/multiplayer/' })
$bad += @($names | Where-Object { $_ -match 'GEODATA' })     # named canary, kept for clarity
if ($bad.Count) { throw "licensed retail data leaked into $Archive`: $(($bad | Select-Object -Unique) -join ', ')" }

foreach ($req in @('UFO/multiplayer/base.png', 'TFTD/multiplayer/base.png')) {
  if ($names -notcontains $req) { throw "$Archive is missing $req - new game would crash in Globe's ctor" }
}

# Not build output, so every package has to place these deliberately - the WinXP zip
# shipped without either through 8.4.13203 (empty Official server list), and #137 was
# the same class of bug for the install instructions.
foreach ($req in @('rendezvous.json', 'LICENSE.txt', 'HOW_TO_RUN.txt')) {
  if ($names -notcontains $req) { throw "$Archive is missing $req" }
}

Write-Host "package OK ($Archive): coop art + rendezvous.json + LICENSE.txt + HOW_TO_RUN.txt present, no licensed retail data or stray README ($($names.Count) entries)"
