# External-Python Windows candidate: notice and CI handoff

This is a proposal for the publisher's manual, bounded Windows CI run. The app-only candidate **does not redistribute Python or its runtime DLLs**. It requires a separately installed official Python 3.13 and an explicit user-run dependency setup. The publisher owns the new staging and first-run helpers; this document does not prescribe their unreviewed command-line interface. No account credentials, model calls, automatic installer, execution-policy change, login startup, or privileged operations belong in this CI recipe.

Use the exact source snapshot under `platforms/windows/`, the reviewed public repository root `LICENSE-Plip`, pinned official GitHub Actions, `windows-latest` and `timeout-minutes: 20`. Preserve the disabled Codex task gate. CI3's notice bundle is tied to .NET SDK 10.0.403 and resolved runtime packs 10.0.14; the candidate builder must reject different `.runtimeconfig.json` or `.deps.json` versions until their notices are reviewed. Run the full existing Windows regression suite and both Python and native self-tests before assembly. The production CI3 tests used Python 3.12 and Pillow 11; the candidate's proposed Python 3.13/Pillow 13 combination must also be tested on Windows. Pillow 11 has known advisory records and must not be silently shipped.

## Reproduce the four notice inputs without bundling Python

From `platforms/windows/` on a disposable Windows runner with official Python 3.13 x64 and pip already selected by the reviewed setup action:

```powershell
$ErrorActionPreference = 'Stop'
$work = Join-Path $env:RUNNER_TEMP 'atlas-notice-preflight'
New-Item -ItemType Directory -Path $work | Out-Null
$wheels = Join-Path $work 'wheels'
New-Item -ItemType Directory -Path $wheels | Out-Null
$archive = Join-Path $work 'python-3.13.17-embed-amd64.zip'
Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.13.17/python-3.13.17-embed-amd64.zip' -OutFile $archive
$expected = '9e35319bffedab8b36ad44d8f377cb4f1733bcec257a0b6d04d94f01486ddb38'
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw 'Python archive hash mismatch.' }
python -m pip download --disable-pip-version-check --only-binary=:all: --require-hashes --dest $wheels -r requirements-windows-lock.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python collect-python-notices.py --archive $archive --wheelhouse $wheels --output (Join-Path $work 'python-notices')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
.\stage-candidate-notices.ps1 -RuntimeNotices (Join-Path $work 'python-notices') -OutputDir (Join-Path $work 'candidate-notices')
```

The Python ZIP and wheel files are read as archives for license extraction, not executed or included in the app-only package. `collect-python-notices.py` verifies every archive hash. `stage-candidate-notices.ps1` verifies the saved source notices' hashes and generates `PYTHON.txt`, `PYTHON-PACKAGES.txt`, `DOTNET.txt`, `NUGET.txt`, and the nested original notice directories. The latter two files are indexes into retained exact HTML, RTF and text files, not claims of legal clearance. External setup may later install the pinned wheels on the user's machine; including their notices is conservative. Do not copy `$work`, the ZIP, wheelhouse, runner Python installation, temporary profiles, or `atticus.json` into a public package.

## Publisher assembly and relocation checks

Once the publisher's app-only staging helper is reviewed, give it only the freshly published .NET output, the explicitly reviewed source/UI files, `candidate-notices`, the upstream Windows MIT license and the root `LICENSE-Plip`. The package should contain no `runtime/python.exe`, `python3*.dll`, `vcruntime140*.dll` supplied by the CPython ZIP, absolute runner source/venv paths, or personal configuration. This does not remove or reclassify any runtime binaries already part of the self-contained .NET app; review each actual published file against Microsoft's .NET Windows license guidance.

Move the candidate to a new directory before testing. In a fresh scratch user profile with no owner credentials, verify that the publisher's first-run instructions/helper do not install, sign in, alter execution policy or enable startup until the user explicitly chooses the documented steps. After an explicit test setup using the isolated runner's officially installed Python and the hash-locked wheel set, verify the app's `Paths.Local/venv` fallback resolves to that user-local venv, imports required modules, and runs `atticus.py --selftest`; run `Atticus.exe --selftest` separately. Assert neither the original staging folder nor source-tree Python/venv is required. Check all external dependency instructions, including the [official Microsoft WebView2 Runtime setup](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution), and keep Claude Code sign-in a separate user action. Reset scratch environment after the test.

Headless success is not evidence of working microphone, onboarding, tray, approvals, or Codex on a user's machine. Run an interactive clean-Windows review before treating it as usable. The notice indexes and version checks are not legal advice or proof of complete coverage. NuGet, native DLL, Pillow and first-run security checks still require review against the exact assembled package, and vulnerability sources must be checked again at release time.
