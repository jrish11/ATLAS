# Native approval development checkpoint

This branch exports the isolated native prototype from source `86f2541fcff3df61e6ff037328be431832bd160f`. It is not imported by production. All Claude/Codex execution in the Windows preview remains disabled.

The manual 20-minute standard Windows CI compiles and runs custom C# and Python fixtures with fake processes and newly created runner-temporary directories. It does not open dialogs, read real accounts, request permissions, invoke Codex, spend API usage, publish artifacts or enable any AI gate.

Known review gates remain: actual provider/Windows sandbox enforcement, native executable provenance and protocol compatibility, legacy worker-pipe cancellation semantics, handle inheritance and interactive native dialog behavior. Configuration echoes and passing fake tests are not proof of isolation. The legacy Python worker approval bridge must not become production authority; provider request binding belongs to the native host.

The public Windows download remains held. No website release or stable version is changed by this development branch.

Dispatch the existing `atlas-windows-validation.yml` workflow with ref `development/windows-native-approval`. That branch intentionally runs only the `native-development` fixture job; the default branch retains its restricted-package validation workflow.

The first development Windows run reached the C# compiler and found a test variable-shadowing error; no native fixtures ran. This revision fixes that error and adds provider-request deduplication and directly linked pending-grant revocation. Ten Python fixtures passed, while revised C# behavior awaits the next Windows run. No grant already delivered to a provider can be recalled with certainty.

The next Windows run compiled successfully but failed while deleting the disposable junction fixture, potentially masking its primary guard result. This revision reads back and removes only its own reparse tag before cleanup and preserves original failures. The exact previous cause is not claimed. The runner lacked 8.3 aliases; that case remains unverified.

[Native Windows CI 41238822580](https://github.com/jrish11/ATLAS/actions/runs/41238822580) passed the compiled custom native suite and ten Python fixtures at source `5bcf948`. The guard detected the tested in-place junction mutation. This revision additionally rechecks project identity immediately before queued thread, turn and approval writes; its new fixtures require Windows revalidation. This narrows a race without proving descriptor-bound isolation. No production code is wired to this prototype.

## Final native fixture result — 2026-10-31 UTC

[Windows run 41239065591](https://github.com/jrish11/ATLAS/actions/runs/41239065591) passed at exported code commit `97f78b7157f375a2a664ec30b0419c916cea5348`, corresponding to source `86f2541fcff3df61e6ff037328be431832bd160f`. Ten Python protocol tests passed, and the custom C# executable compiled and passed its fake-child/provider, cancellation, revocation, duplicate-request and queued-project cases. The tested in-place junction mutation was detected by the guard. The volume did not provide 8.3 aliases, so that case is unverified. Seven independent static checks found no new blocker in the final dispatch-check diff.

These are synthetic protocol/native integration checks, not a live AI task or interactive UI test. No real account/provider, model/API request, native approval dialog, installation, permission change or app release occurred. The queued-project fixtures assert no forbidden output marker; a filler-write timeout could also prevent that marker, so these cases are not exhaustive race proof. Production Python, native entry points and the production project file remain byte-identical to restricted main. The development branch is not merged and its prototype has no production caller.

Before enabling Windows AI, implement and verify the trusted production broker, supported executable/protocol provenance, actual OS sandbox read/write/network denials, process/handle containment and interactive owner consent/cancellation. The retired worker-pipe experiment is not approval authority. Already-started writes/actions can have uncertain outcomes. Public Windows downloads remain held.

## Suspended containment development revision

This revision adds suspended Win32 creation, an explicit three-handle stdio inheritance list and job assignment before process resume. Independent static review found no new blocker in the bounded launch/cleanup change; actual Windows fixtures remain required. The updated queue test synchronizes writer arrival so a filler timeout cannot substitute for the intended race assertion.

The new native broker is immutable OFF, unwired and not part of the production application. Official CLI digest metadata and MXC probe scaffolding are present, but no actual official Windows binary bytes have been independently hashed or executed by this checkpoint. The default CI runs fake processes only; it does not invoke the opt-in Python sandbox probe, real accounts, a model or administrator setup. Parent-path/helper provenance, actual OS sandbox enforcement and interactive consent remain release gates.

## Authorized no-account OS probe checkpoint

Suspended-launch source `2430789` passed Windows CI 41240060152 (twelve Python fixtures plus the native custom suite). This later branch first revalidates fake fixtures, then downloads only the official OpenAI 0.166.0 Windows package into a fresh runner-temporary directory. The staging helper verifies archive SHA256 d559bb88e74d471265857b93b7f19bc250dae527673b9191b33534478093f6bc, rejects unsafe archive members, and checks the exact manifest plus six executable hashes. Nothing is installed or published.

Only after those checks, the native test harness runs an explicit MXC command in a kill-on-close job created before resume, with an empty scratch profile and CODEX_HOME. TEMP is separate from the forbidden sibling. The test checks a permitted project write, a forbidden sibling write and loopback denial against its own reachable listener. Output and time are bounded; no account, model, API key, installer, administrator setup, fallback sandbox or owner-machine setting is used. Unsupported MXC or a failed boundary stops the job; it is not converted to success. Even a pass would establish only these tested boundaries, not full production isolation. The native broker remains OFF and the public Windows download is held.

The first real-CLI attempt (Windows CI 41240704625) passed fake suites, archive guards and actual official archive/manifest/six-executable hash verification, but stopped before MXC evaluation because the empty scratch CODEX_HOME directory had not been created. This revision creates that directory and tests its placement; diagnostics redact escaped scratch paths as well. No sandbox support or enforcement result is inferred from that failed preflight.
