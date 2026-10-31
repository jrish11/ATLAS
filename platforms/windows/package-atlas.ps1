# Assemble a candidate folder from separately supplied, reviewed build inputs.
# This does not download runtimes, install software, zip, sign, or publish.
param(
  [Parameter(Mandatory=$true)][string]$BuildDir,
  [Parameter(Mandatory=$true)][string]$RuntimeDir,
  [Parameter(Mandatory=$true)][string]$NoticeDir,
  [Parameter(Mandatory=$true)][string]$PlipLicense,
  [Parameter(Mandatory=$true)][string]$OutputDir
)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if ($env:OS -ne 'Windows_NT') { throw 'Windows is required.' }
$build = (Resolve-Path -LiteralPath $BuildDir).Path
$runtime = (Resolve-Path -LiteralPath $RuntimeDir).Path
$notices = (Resolve-Path -LiteralPath $NoticeDir).Path
$plip = (Resolve-Path -LiteralPath $PlipLicense).Path
if (-not (Test-Path -LiteralPath $plip -PathType Leaf) -or (Get-Item -LiteralPath $plip).Length -eq 0) { throw 'Plip license must be a nonempty file.' }
if (Test-Path -LiteralPath $OutputDir) { throw 'OutputDir must not already exist.' }
if (-not (Test-Path -LiteralPath (Join-Path $build 'Atticus.exe'))) { throw 'Compiled Atticus.exe missing.' }
if (-not (Test-Path -LiteralPath (Join-Path $runtime 'python.exe'))) { throw 'Reviewed Python runtime missing python.exe.' }
# Notice sets are tied to CI3's exact dependency versions; reject drift.
$configPath = Join-Path $build 'Atticus.runtimeconfig.json'
$depsPath = Join-Path $build 'Atticus.deps.json'
if (-not (Test-Path -LiteralPath $configPath) -or -not (Test-Path -LiteralPath $depsPath)) { throw 'Runtime configuration or dependency manifest missing.' }
$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$frameworks = @($config.runtimeOptions.includedFrameworks)
foreach ($framework in @('Microsoft.NETCore.App', 'Microsoft.WindowsDesktop.App')) {
  $foundFrameworks = @($frameworks | Where-Object { $_.name -eq $framework -and $_.version -eq '10.0.14' })
  if ($foundFrameworks.Count -ne 1) { throw "Runtime version differs from reviewed notice set: $framework" }
}
$reviewed = @{}
$dotManifest = Get-Content -LiteralPath (Join-Path $notices 'dotnet-10.0.14\manifest.json') -Raw | ConvertFrom-Json
foreach ($entry in $dotManifest.packages.PSObject.Properties) { $reviewed[$entry.Name.ToLowerInvariant()] = $entry.Value.version }
$nugetManifest = Get-Content -LiteralPath (Join-Path $notices 'nuget-ci3\manifest.json') -Raw | ConvertFrom-Json
foreach ($entry in $nugetManifest.packages) { $reviewed[$entry.id.ToLowerInvariant()] = $entry.version }
$deps = Get-Content -LiteralPath $depsPath -Raw | ConvertFrom-Json
foreach ($entry in $deps.libraries.PSObject.Properties) {
  if ($entry.Value.type -notin @('package', 'runtimepack')) { continue }
  $parts = $entry.Name -split '/', 2
  if ($parts.Count -ne 2) { throw 'Invalid dependency manifest entry.' }
  $name = $parts[0] -replace '^runtimepack\.', ''
  if (-not $reviewed.ContainsKey($name.ToLowerInvariant()) -or $reviewed[$name.ToLowerInvariant()] -ne $parts[1]) { throw "Unreviewed dependency version: $($entry.Name)" }
}
foreach ($file in @('PYTHON.txt', 'PYTHON-PACKAGES.txt', 'DOTNET.txt', 'NUGET.txt')) {
  $path = Join-Path $notices $file
  if (-not (Test-Path -LiteralPath $path) -or (Get-Item -LiteralPath $path).Length -eq 0) { throw "Required reviewed notice missing: $file" }
}
# Refuse common local credential or profile files in inputs; this is not a complete secret audit.
$forbidden = @('.env', 'settings.json', 'atticus.json', 'memory.md', 'recent.jsonl', 'log.jsonl', 'license.key')
foreach ($source in @($build, $runtime, $notices)) {
  $bad = Get-ChildItem -LiteralPath $source -Recurse -Force -File | Where-Object { $_.Name -in $forbidden -or $_.Extension -in @('.pem', '.pfx', '.key') } | Select-Object -First 1
  if ($bad) { throw "Unexpected local state or credential-like file in packaging input: $($bad.Name)" }
}
New-Item -ItemType Directory -Path $OutputDir | Out-Null
$out = (Resolve-Path -LiteralPath $OutputDir).Path
Copy-Item -Path (Join-Path $build '*') -Destination $out -Recurse
Copy-Item -LiteralPath $runtime -Destination (Join-Path $out 'runtime') -Recurse
Copy-Item -LiteralPath $notices -Destination (Join-Path $out 'licenses') -Recurse
Copy-Item -LiteralPath 'LICENSE' -Destination (Join-Path $out 'LICENSE-ATTICUS.txt')
Copy-Item -LiteralPath $plip -Destination (Join-Path $out 'LICENSE-Plip.txt')
Copy-Item -LiteralPath 'atticus.py', 'winctl.py', 'codex_account.py', 'codex_provider.py', 'atlas_codex_task.py' -Destination $out
New-Item -ItemType Directory -Path (Join-Path $out 'integrations'), (Join-Path $out 'ui') | Out-Null
Copy-Item -Path 'integrations\*.py' -Destination (Join-Path $out 'integrations')
Copy-Item -Path 'ui\*.html', 'ui\*.js', 'ui\AppIcon.ico', 'ui\AppIcon.png' -Destination (Join-Path $out 'ui')
Copy-Item -LiteralPath 'WINDOWS-PACKAGE-README.txt' -Destination (Join-Path $out 'README.txt')
$py = Join-Path $out 'runtime\python.exe'
& $py -I -c 'import sys; assert sys.version_info >= (3, 11); import mss, PIL, psutil, uiautomation, comtypes'
if ($LASTEXITCODE -ne 0) { throw 'Bundled Python/dependency import check failed; candidate is not releasable.' }
$testProfile = Join-Path $env:TEMP ('atlas-package-test-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $testProfile | Out-Null
$oldProfile = $env:ATTICUS_DIR
try {
  $env:ATTICUS_DIR = $testProfile
  & $py -X utf8 (Join-Path $out 'atticus.py') --selftest
  if ($LASTEXITCODE -ne 0) { throw 'Bundled Python self-test failed; candidate is not releasable.' }
  $native = Start-Process -FilePath (Join-Path $out 'Atticus.exe') -ArgumentList '--selftest' -PassThru -Wait
  if ($native.ExitCode -ne 0) { throw 'Native self-test failed; candidate is not releasable.' }
} finally { $env:ATTICUS_DIR = $oldProfile; Remove-Item -LiteralPath $testProfile -Recurse -Force }
Write-Host "Candidate assembled: $out"
Write-Host 'Not a release: review notices and test a relocated copy on a clean Windows machine.'
