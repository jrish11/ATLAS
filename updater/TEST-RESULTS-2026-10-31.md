# Signed updater validation — 2026-10-31

Development base: `c8de0c2d1f7a0b257d987dc98c6c829d7961e7a0` (First Light build 3). Isolated feature branch; this does not replace the later phone/frontend freeze or any delivered release.

Final offline aggregate (`bash updater/tests/run_all.sh`) passed:

| Component | Evidence |
| --- | --- |
| Exact-byte manifest verification | 83 assertions with ephemeral Ed25519 signatures |
| Compiled production trust gate | 14 assertions; empty roots reject |
| URLSession mocked transport | 38 assertions; chunks, size limits, errors, cancellation, concurrent transfers |
| Filesystem transaction | 126 assertions; real atomic exchange, backup/rollback, six abrupt subprocess crashes, cancellation, replay, locks, links, ACLs and changed identities |
| Coordinator and private receipt | 18 assertions; no-network disabled gate, concurrency, monotonic state, symlink and malformed-state rejection |
| Native platform/process/cleanup | 17 assertions; deployment-command conflicts, CPU binding, timeouts, cancellation, descriptor cleanup and outside sentinel preservation |
| Archive integration | 6 assertions; real signed fixture, Python extraction, nested ad-hoc bundle validation and cleanup |
| Installer and local restore | 94 assertions; real temporary signed child processes, parent exit, ACK mismatch, confirmed failure, unknown/live result, interlocks, one-shot restore, extractor dependencies, SIGPIPE, replay and valid backup/journal substitution before/after confirmation |
| Python hostile-input suite | 21 tests |
| Native update window | Swift typecheck with warnings treated as errors; no interactive AppKit claim |

That is **396 Swift assertions and 21 Python tests**, rather than 417 end-to-end application tests. Fixtures never use an installed app, owner profile, API key, provider account, microphone or real release-signing key.

A separate optional real public-transport probe fetched the existing public v3.6 ZIP into memory: 2,127,724 bytes; SHA-256 `2c1335d796fd53880dbb8dbcc57733493b39e952dd5b9626fcc2ab0adf5d259e`; one measured download took **0.532 seconds**. It exercised real GitHub HTTPS and release-asset redirects. It did not extract/install that release or verify a future signed feed. This one sample is not a median, slow-case or general command-latency benchmark.

An isolated macOS arm64 development app was compiled without launching or installing it. `codesign --verify --deep --strict` passed, including the new helper. It is ad-hoc signed, not Developer ID signed or notarized. No updater-specific compiler warnings remained; existing source warnings were retained.

## Blocked/unverified

- Production trust roots are deliberately empty. No publisher key creation, Keychain access, signed feed publication or automatic update activation occurred.
- The first updater-protocol installation is manual; old releases without the startup interlock are ineligible for automatic replacement.
- Native button interaction, actual owner-app quit/relaunch, the physical MacBook, and an activated real signed feed remain unverified.
- Local-backup restore uses explicit owner consent, exact private journal identity and code signature. It is not a publisher-signed downgrade release. Unknown crash outcomes require inspection, not blind retry.
- Same-user hostile processes are not isolated by this mechanism. Least-privilege same-owner filesystem checks reduce races but do not constitute an OS sandbox.
- No API/model requests or credential transfers were used in this validation. Existing provider testing budgets are unchanged.

The final restore request binds the exact old build/digest displayed by the native confirmation. Replacing both a valid backup and its journal metadata before handoff or after readiness is rejected without swapping or launching. A valid signed feed matching the installed release returns a non-installable current status rather than an update failure.
