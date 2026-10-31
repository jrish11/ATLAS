# Prepare a test-only runtime using hash-locked official CPython and PyPI files.
# Requires a trusted Windows Python 3.13 with pip. No login, install or publication.
param([Parameter(Mandatory=$true)][string]$OutputDir)
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'Windows is required.' }
Set-Location $PSScriptRoot
if (Test-Path -LiteralPath $OutputDir) { throw 'OutputDir must not exist.' }
& python -c 'import sys, struct; assert sys.version_info[:2] == (3,13) and struct.calcsize("P") == 8'
if ($LASTEXITCODE -ne 0) { throw 'Build Python must be CPython 3.13 x64.' }
New-Item -ItemType Directory -Path $OutputDir | Out-Null
$out = (Resolve-Path -LiteralPath $OutputDir).Path
$wheelhouse = Join-Path $out 'wheelhouse'
$runtime = Join-Path $out 'runtime'
New-Item -ItemType Directory -Path $wheelhouse, $runtime | Out-Null
$zip = Join-Path $out 'python-3.13.17-embed-amd64.zip'
Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.13.17/python-3.13.17-embed-amd64.zip' -OutFile $zip
$expected = '9e35319bffedab8b36ad44d8f377cb4f1733bcec257a0b6d04d94f01486ddb38'
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $zip).Hash.ToLowerInvariant() -ne $expected) { throw 'CPython archive hash mismatch.' }
python -m pip download --disable-pip-version-check --only-binary=:all: --require-hashes --dest $wheelhouse -r requirements-windows-lock.txt
if ($LASTEXITCODE -ne 0) { throw 'Hash-locked wheel download failed.' }
Expand-Archive -LiteralPath $zip -DestinationPath $runtime
# The embeddable distribution is isolated; opt into its bundled dependencies only.
@('python313.zip', '.', '..', 'site-packages', 'import site') | Set-Content -LiteralPath (Join-Path $runtime 'python313._pth') -Encoding ascii
python -m pip install --disable-pip-version-check --no-index --find-links $wheelhouse --only-binary=:all: --require-hashes --no-compile --target (Join-Path $runtime 'site-packages') -r requirements-windows-lock.txt
if ($LASTEXITCODE -ne 0) { throw 'Hash-locked dependency staging failed.' }
& (Join-Path $runtime 'python.exe') -I -c 'import sys, struct; assert sys.version_info[:3] == (3,13,17) and struct.calcsize("P") == 8; import mss, PIL, psutil, uiautomation, comtypes'
if ($LASTEXITCODE -ne 0) { throw 'Embedded dependency import check failed.' }
python collect-python-notices.py --archive $zip --wheelhouse $wheelhouse --output (Join-Path $out 'notices')
if ($LASTEXITCODE -ne 0) { throw 'Notice extraction failed.' }
Write-Host "Runtime candidate: $runtime"
Write-Host "Unreviewed Python notices: $out\notices"
Write-Host 'Candidate only: resolve remaining third-party and .NET notices; test relocated on Windows.'
