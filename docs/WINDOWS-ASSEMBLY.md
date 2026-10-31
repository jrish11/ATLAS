# Windows setup-required preview assembly

The Windows source is a separate experimental port. It has no Terra/API parity claim and Codex task dispatch remains disabled. The restricted Windows CI checkpoint below passed compilation, regression tests, package assembly and relocation. A trusted provider boundary and interactive verification remain release gates.

The manual `ATLAS Windows validation` workflow uses standard Windows runners with a 20-minute limit, pinned official actions, SDK 10.0.403 and Python 3.13.17. It installs hash-locked current candidate dependencies, executes the regression suite, publishes the .NET app, validates exact .NET/NuGet notice versions, and assembles a setup-required ZIP. A build receipt binds all copied compiled output; x64 PE and dependency inventory are checked. It then relocates the package and checks explicit setup cancellation, confirmed per-user environment creation, dependency imports, Python/native self-tests and every package hash.

The ZIP redistributes no Python interpreter or Python VC runtime DLLs. Owners must install official Python 3.13 x64 (3.13.17 or a newer 3.13 patch), then explicitly run `Setup-Windows.cmd`. The helper requires typed `SETUP`, uses official PyPI and hash-locked binary dependencies, preserves existing runtimes and marks incomplete installs without deleting them. WebView2 Runtime setup remains owner-controlled. AI sign-in is not required or supported in the restricted preview. It does not alter execution policy, enable startup or grant permissions.

A successful headless run is not interactive verification of tray, microphone, approvals, onboarding or normal conversation. CI artifact retention is temporary; a public binary release requires inspection of the actual assembled archive, licenses and hashes. No automatic publication occurs in this workflow.

## Security restriction after independent review

The inherited unsandboxed Claude route accepted writable-file approvals. A synthetic test reproduced an approval without native consent; no live action was needed. The public source now disables ALL model launch and tool dispatch, saved shell replay, partial-speech actions and unverified general-control helpers. These gates do not depend on settings or inherited environment variables. Only confirmed owner-triggered local commands remain, labeled unsandboxed. Neither Claude nor Codex sign-in is required or useful for this restricted preview.

CI validated this restricted inspection candidate; public binary download is held pending a trusted provider boundary. CI success is not approval-boundary verification and the candidate must not be advertised as the full Windows ATLAS assistant.

## Verified restricted assembly checkpoint — 2026-10-31 UTC

[Windows CI run 41237532147](https://github.com/jrish11/ATLAS/actions/runs/41237532147) passed at public source `a29fb7b207636e7497ee7576481037c8bc714c56` (Windows source freeze `09583b54d2e00fdcfc9b17fc3ad03bd09b0938dc`). There were 119 unit/fixture tests, zero failures and zero skips. Actual Windows checks also passed .NET compilation, native self-tests before/after relocation, Python self-tests, explicit setup cancellation, real hash-locked dependency installation and imports. These tests made no model/API requests.

Post-download inspection verified 350 files: 349 manifest entries plus the manifest itself, with exact membership and hashes. Five Python resources match the source freeze after Windows CRLF normalization; license/lock bytes are preserved exactly. No Python interpreter, Python VC runtime DLLs, bytecode caches, user state or known owner-private markers were found. The inspection ZIP is 62,475,382 bytes, SHA256 `da19381576d2ccaa901700cfe85714a8984a934875c87e9577a82e742f3afe86`. It is retained locally/temporarily as a CI review artifact, not a published app release or website download.

Independent review passed seven boundary tests plus 13 extra no-dispatch probes. This verifies the disabled state, not a trusted AI execution boundary. A protected native approval broker and supported isolation still need implementation and adversarial verification. Interactive tray, microphone, onboarding and desktop control remain unverified. Signed Windows publishing and a stable updater are not configured.

The earlier assembly run passed but post-download inspection found two unmanifested Python cache files. The final run disables bytecode generation and rejects any extra final file before archiving; no earlier artifact was released.
