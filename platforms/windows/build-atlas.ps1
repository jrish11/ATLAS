# Build a local ATLAS development folder on Windows. Does not install or start the app.
# Prerequisites: .NET 10 SDK, Python 3.11+, Git for Windows, Claude Code, WebView2 runtime.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if ($env:OS -ne 'Windows_NT') { throw 'This build requires Windows.' }
if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) { throw 'Install the .NET 10 SDK first.' }
if (-not (Get-Command py -ErrorAction SilentlyContinue)) { throw 'Install Python 3.11 or later with the Python launcher first.' }
$venv = Join-Path $PSScriptRoot '.venv-atlas'
if (-not (Test-Path "$venv\Scripts\python.exe")) { & py -3 -m venv $venv; if ($LASTEXITCODE) { throw 'Could not create Python environment.' } }
& "$venv\Scripts\python.exe" -c 'import sys; assert sys.version_info >= (3,11), "Python 3.11 or later is required"'
if ($LASTEXITCODE) { throw 'Python version check failed.' }
& "$venv\Scripts\python.exe" -m pip install -r requirements.txt
if ($LASTEXITCODE) { throw 'Python dependency installation failed.' }
$out = Join-Path $PSScriptRoot 'dist\ATLAS'
New-Item -ItemType Directory -Force $out | Out-Null
& dotnet publish win\Atticus -c Release -r win-x64 --self-contained -p:DebugType=none -o $out --nologo
if ($LASTEXITCODE) { throw 'Build failed.' }
Copy-Item atticus.py, winctl.py, codex_account.py, codex_provider.py, atlas_codex_task.py $out -Force
New-Item -ItemType Directory -Force "$out\integrations", "$out\ui" | Out-Null
Copy-Item integrations\*.py "$out\integrations" -Force
Copy-Item ui\*.html, ui\*.js, ui\AppIcon.ico, ui\AppIcon.png "$out\ui" -Force
@{ python = "$venv\Scripts\python.exe"; source = $PSScriptRoot; version = 'ATLAS development build' } | ConvertTo-Json | Set-Content "$out\atticus.json" -Encoding utf8
Write-Host "Build complete: $out\Atticus.exe"
Write-Host 'Development build only: keep the source and .venv-atlas in place. No installer or portable release has been produced.'
