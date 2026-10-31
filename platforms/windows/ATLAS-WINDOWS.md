# ATLAS for Windows — development source

This is an experimental ATLAS adaptation of [FindlayHi/atticus-windows](https://github.com/FindlayHi/atticus-windows), itself a Windows port of [SaarthurR/atticus-mac](https://github.com/SaarthurR/atticus-mac). The original MIT license is in `LICENSE`. Upstream commit: `657cc26d9cac48ce6951958fc4b2b519787a0af6`.

**Status: source only. No Windows build or runtime test has been performed. This is not a downloadable release.** It currently uses Claude Code and a supported Claude account, as upstream does. A separate experimental Codex account-status probe is available in Intelligence settings. It only reads the account type and does not start a task, perform sign-in, or store credentials. A Codex task adapter and provider selection route are implemented but gated off until native Windows verification; the Codex watcher upstream is not an AI backend. Do not advertise this as a ChatGPT-powered app.

The ATLAS display name, default configuration directory, local runtime directory, login entry, and single-instance identifiers are separated from Atticus. The upstream updater is disabled so it cannot replace ATLAS with upstream code. Internal names, icons, and some copy still refer to Atticus. The original upstream installer and `build.ps1` are retained for attribution/reference; **do not run them to build ATLAS** because they install Atticus and enable startup.

## Build on a Windows test machine

1. Install .NET 10 SDK, Python 3.11+, Git for Windows, Microsoft Edge WebView2 Runtime, and Claude Code. Sign into Claude Code with a supported account.
2. From a PowerShell window in this source directory, run `powershell -ExecutionPolicy Bypass -File .\build-atlas.ps1`. This installs Python dependencies into `.venv-atlas` and downloads .NET packages as needed; it does not install or start the app.
3. Run `dist\ATLAS\Atticus.exe --selftest`, then `.\.venv-atlas\Scripts\python.exe -m unittest discover -s tests -v` and `$env:PYTHONUTF8='1'; .\.venv-atlas\Scripts\python.exe atticus.py --selftest` with `ATTICUS_DIR` set to a disposable directory. Manually test onboarding, microphone, hotkey, approvals, account login, and co-existence with Atticus on Windows before any release.
4. The generated folder depends on the source tree's `.venv-atlas` and is not a distributable installer. A reproducible packaging process, malware scanning, code signing, and clean-machine tests remain to be done before offering public downloads.

The app can control files and applications. Review the upstream safety model and test its approval behavior on Windows. No personal settings, credentials, or profile were copied into this checkout.

## Account adapter checks

`python -m unittest discover -s tests -p test_codex_account.py -v` tests the JSONL protocol with a fake transport and no account or model calls. The account check follows the `initialize`, `initialized`, and `account/read` messages in the locally generated Codex app-server schema, with refresh disabled. It does not prove that Codex can run safely on Windows. The task adapter derives from the separate Mac ATLAS fork’s `codex_provider.py`; it preflights scoped permissions and inherited tools, binds events to the active turn, and denies all approval requests in this Windows route. It has no Claude integration bridge, screenshots, or action approval UI. The provider selection stays disabled via `WINDOWS_CODEX_VERIFIED = False`, and the Python worker independently enforces that gate. Fake-server tests do not verify Windows process launch, real sandbox enforcement, Windows job termination, or user-visible cancellation. Those require native testing and review before the gate can be changed. The Windows UI requests cancellation through a per-worker signal, and the worker sends Codex `turn/interrupt`. It waits for a terminal event and reports an unknown outcome on disconnect or a five-second timeout; the UI has an eight-second process-tree fallback. Even a confirmed interruption can leave partial effects. The Windows signal, process lifecycle, and UI have not been verified on Windows.

Run the deterministic task and permission tests with `python -m unittest discover -s tests -p "test_atlas_codex*.py" -v`; they make no real model calls.
