# Pinned Windows runtime candidate: CI handoff

This is a CI candidate, not a released runtime. `prepare-embedded-python.ps1` uses the official x64 CPython 3.13.17 embeddable ZIP, SHA-256 `9e35319bffedab8b36ad44d8f377cb4f1733bcec257a0b6d04d94f01486ddb38`, matching Python.org's [published SPDX SBOM](https://www.python.org/ftp/python/3.13.17/python-3.13.17-embed-amd64.zip.spdx.json). Python 3.13.17 was the latest maintained 3.13 Windows release listed by Python.org when checked on October 31, 2026. Matching wheel artifacts exist for every pinned requirement, but actual Windows installation and compatibility remain untested. Recheck current security updates before publication. [Official Windows releases](https://www.python.org/downloads/windows/)

The exploratory packaging lock does not change production `requirements.txt`. PyPI version metadata listed 81 advisory records for current production Pillow 11.0.0 (including aliases); proposed Pillow 13.0.0 has zero records in that metadata as checked on October 31, 2026, which is not proof of safety. The proposed upgrade requires full compatibility and Windows testing. The five exact wheel hashes in `requirements-windows-lock.txt` were independently verified against PyPI JSON metadata for mss 9.0.2, Pillow 13.0.0, psutil 6.1.0, uiautomation 2.0.29 and comtypes 1.4.17. `collect-python-notices.py` verifies those hashes and extracts the actual license texts from each wheel and the CPython archive into `PYTHON.txt` and `PYTHON-PACKAGES.txt`. Local extraction succeeded without executing a Windows binary. These are partial notices only, not a complete legal review.

Suggested subsequent Windows CI steps, to be applied only by the publisher after the source and tests pass and the listed files are reviewed and exported into `platforms/windows/`:

```powershell
# Run from platforms/windows, after setup-python 3.13 x64 and a passing dotnet publish.
.\prepare-embedded-python.ps1 -OutputDir "$env:RUNNER_TEMP\atlas-runtime-stage"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
# Stage hash-verified exact notice files and four index/input files. These
# indexes do not constitute legal clearance and are tied to CI3 versions.
.\stage-candidate-notices.ps1 -RuntimeNotices "$env:RUNNER_TEMP\atlas-runtime-stage\notices" `
  -OutputDir "$env:RUNNER_TEMP\atlas-reviewed-notices"
.\package-atlas.ps1 -BuildDir "$env:RUNNER_TEMP\atlas-build" `
  -RuntimeDir "$env:RUNNER_TEMP\atlas-runtime-stage\runtime" `
  -NoticeDir "$env:RUNNER_TEMP\atlas-reviewed-notices" `
  -PlipLicense "../../LICENSE-Plip" `
  -OutputDir "$env:RUNNER_TEMP\atlas-candidate"
$relocated = Join-Path $env:RUNNER_TEMP 'atlas-relocated\ATLAS'
New-Item -ItemType Directory -Path (Split-Path $relocated) -Force | Out-Null
Move-Item -LiteralPath "$env:RUNNER_TEMP\atlas-candidate" -Destination $relocated
$env:ATTICUS_DIR = Join-Path $env:RUNNER_TEMP 'atlas-relocation-state'
New-Item -ItemType Directory -Path $env:ATTICUS_DIR -Force | Out-Null
$env:ATLAS_EXPECT_ROOT = $relocated
& "$relocated\runtime\python.exe" -I -c 'import os, pathlib, atticus, winctl, integrations, codex_account, codex_provider, atlas_codex_task, mss, PIL, psutil, uiautomation, comtypes; root = pathlib.Path(os.environ["ATLAS_EXPECT_ROOT"]).resolve(); assert all(pathlib.Path(m.__file__).resolve().is_relative_to(root) for m in (atticus, winctl, integrations, codex_account, codex_provider, atlas_codex_task, mss, PIL, psutil, uiautomation, comtypes))'
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& "$relocated\runtime\python.exe" -X utf8 "$relocated\atticus.py" --selftest
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$p = Start-Process -FilePath "$relocated\Atticus.exe" -ArgumentList '--selftest' -PassThru -Wait
if ($p.ExitCode -ne 0) { throw 'Relocated native self-test failed' }
```

The staging script verifies collected notice hashes and creates the four required inputs. DOTNET.txt and NUGET.txt are indexes pointing to the exact retained files; inspect the full directories, including HTML and RTF. The assembler rejects runtime and .deps versions absent from the CI3 reviewed manifest. Neither these checks nor the indexes prove license completeness. Open items include: Microsoft Windows .NET runtime pack LICENSE and THIRD-PARTY-NOTICES from the exact versions resolved; runtime Windows-license classifications; Pillow's bundled native image libraries and their notices; CPython embeddable components (including OpenSSL, sqlite, expat, libffi, and Microsoft Visual C++ runtime) and any additional required notices or redistribution terms; uiautomation's native DLL provenance; NuGet and Whisper native transitive dependencies. The [publisher's direct dependency audit](https://github.com/jrish11/ATLAS) is useful but does not replace inspection of actual resolved assets. Use the official Python SBOM as an inventory aid; entries marked NOASSERTION are not license conclusions.

After `dotnet publish`, collect an inspectable inventory of exact resolved versions, published-file hashes and available license/notice files (this does not generate a legally complete `DOTNET.txt` or `NUGET.txt`):

```powershell
python harvest-dotnet-notices.py `
  --assets win/Atticus/obj/project.assets.json `
  --deps "$env:RUNNER_TEMP\atlas-build\Atticus.deps.json" `
  --publish-dir "$env:RUNNER_TEMP\atlas-build" `
  --nuget-root "$env:USERPROFILE\.nuget\packages" `
  --dotnet-root "$env:DOTNET_ROOT" `
  --output "$env:RUNNER_TEMP\atlas-dotnet-inventory"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

Review `manifest.json`, including packages with no notice found. Package-cache absence can mean another SDK location or runtime pack resolution mechanism; it does not mean no notice is required. Inspect the exact resolved .NET runtime pack versions and their published native binaries against Microsoft's Windows runtime license information; resolve mismatches before release.

The scripts, .NET change, and proposed relocation smoke have not been executed on Windows. No CI artifacts or releases should be published until their output, exact license files, security and privacy checks are reviewed. Passing headless smoke tests will not verify microphone, tray, onboarding, approvals, cancellation, or Codex Windows sandbox behavior.
