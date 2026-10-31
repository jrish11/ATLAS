# Windows setup-required preview assembly

The Windows source is a separate experimental port. It has no Terra/API parity claim and Codex task dispatch remains disabled. The previous headless Windows CI run passed compilation and regression tests; assembled-package and relocation validation is the next release gate.

The manual `ATLAS Windows validation` workflow uses standard Windows runners with a 20-minute limit, pinned official actions, SDK 10.0.403 and Python 3.13.17. It installs hash-locked current candidate dependencies, executes the regression suite, publishes the .NET app, validates exact .NET/NuGet notice versions, and assembles a setup-required ZIP. A build receipt binds all copied compiled output; x64 PE and dependency inventory are checked. It then relocates the package and checks explicit setup cancellation, confirmed per-user environment creation, dependency imports, Python/native self-tests and every package hash.

The ZIP redistributes no Python interpreter or Python VC runtime DLLs. Owners must install official Python 3.13 x64 (3.13.17 or a newer 3.13 patch), then explicitly run `Setup-Windows.cmd`. The helper requires typed `SETUP`, uses official PyPI and hash-locked binary dependencies, preserves existing runtimes and marks incomplete installs without deleting them. WebView2 Runtime and Claude Code installation/sign-in remain separate owner actions. It does not alter execution policy, enable startup or grant permissions.

A successful headless run is not interactive verification of tray, microphone, approvals, onboarding or normal conversation. CI artifact retention is temporary; a public binary release requires inspection of the actual assembled archive, licenses and hashes. No automatic publication occurs in this workflow.
