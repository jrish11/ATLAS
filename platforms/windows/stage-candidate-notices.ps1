# Assemble exact audited source notices for experimental CI; not legal clearance.
param(
  [Parameter(Mandatory=$true)][string]$RuntimeNotices,
  [Parameter(Mandatory=$true)][string]$OutputDir
)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (Test-Path -LiteralPath $OutputDir) { throw 'Notice output must not exist.' }
$runtime = (Resolve-Path -LiteralPath $RuntimeNotices).Path
$base = (Resolve-Path -LiteralPath 'notices').Path
function Check-Hash([string]$Path, [string]$Expected) {
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Notice is missing: $Path" }
  if ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Expected.ToLowerInvariant()) { throw "Notice hash mismatch: $Path" }
}
$dot = Join-Path $base 'dotnet-10.0.14'
$nuget = Join-Path $base 'nuget-ci3'
$native = Join-Path $base 'python-native-3.13.17'
$dotManifest = Get-Content -LiteralPath (Join-Path $dot 'manifest.json') -Raw | ConvertFrom-Json
foreach ($entry in $dotManifest.notices) { Check-Hash (Join-Path $dot $entry.file) $entry.sha256 }
Check-Hash (Join-Path $dot $dotManifest.additional_license.file) $dotManifest.additional_license.sha256
$nugetManifest = Get-Content -LiteralPath (Join-Path $nuget 'manifest.json') -Raw | ConvertFrom-Json
foreach ($package in $nugetManifest.packages) { foreach ($entry in $package.extracted) { Check-Hash (Join-Path $nuget $entry.file) $entry.sha256 } }
foreach ($entry in $nugetManifest.exact_source_supplements) { Check-Hash (Join-Path $nuget $entry.file) $entry.sha256 }
$nativeManifest = Get-Content -LiteralPath (Join-Path $native 'manifest.json') -Raw | ConvertFrom-Json
foreach ($entry in $nativeManifest.entries) { Check-Hash (Join-Path $native $entry.file) $entry.sha256 }
foreach ($name in @('PYTHON.txt', 'PYTHON-PACKAGES.txt')) {
  $expected = (Get-FileHash -LiteralPath (Join-Path $native $name) -Algorithm SHA256).Hash
  Check-Hash (Join-Path $runtime $name) $expected
}
New-Item -ItemType Directory -Path $OutputDir | Out-Null
$out = (Resolve-Path -LiteralPath $OutputDir).Path
foreach ($name in @('PYTHON.txt', 'PYTHON-PACKAGES.txt')) { Copy-Item -LiteralPath (Join-Path $runtime $name) -Destination $out }
Copy-Item -LiteralPath $dot -Destination (Join-Path $out 'dotnet-10.0.14') -Recurse
Copy-Item -LiteralPath $nuget -Destination (Join-Path $out 'nuget-ci3') -Recurse
Copy-Item -LiteralPath $native -Destination (Join-Path $out 'python-native-3.13.17') -Recurse
# Indexes name the retained exact texts, including HTML/RTF that cannot be
# faithfully represented by concatenating their bytes into plain text.
@'
Experimental notice index — review required.
.NET 10.0.14 exact license and notices: dotnet-10.0.14/NETCore-LICENSE.txt,
dotnet-10.0.14/NETCore-THIRD-PARTY-NOTICES.txt,
dotnet-10.0.14/WindowsDesktop-LICENSE.txt, and
 dotnet-10.0.14/Microsoft-Dotnet-Library-License.html.
The complete legal review and redistribution decision remain open.
'@ | Set-Content -LiteralPath (Join-Path $out 'DOTNET.txt') -Encoding utf8
@'
Experimental notice index — review required.
Exact CI3 NuGet package notices and source supplements: nuget-ci3/.
The Windows SDK license is nuget-ci3/microsoft-windows-sdk-license.rtf.
Python native source notices: python-native-3.13.17/.
Review each manifest and native dependency; this index is not legal clearance.
'@ | Set-Content -LiteralPath (Join-Path $out 'NUGET.txt') -Encoding utf8
Write-Host "Candidate notices staged at $out; review remains required."
