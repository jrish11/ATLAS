# Native approval development checkpoint

This branch exports the isolated native prototype from source `2430789e08911e135614d92012bb6c5bf3cc6bb5`. It is not imported by production. All Claude/Codex execution in the Windows preview remains disabled.

The manual 20-minute standard Windows CI compiles and runs custom C# and Python fixtures with fake processes and newly created runner-temporary directories. It does not open dialogs, read real accounts, request permissions, invoke Codex, spend API usage, publish artifacts or enable any AI gate.

Known review gates remain: actual provider/Windows sandbox enforcement, native executable provenance and protocol compatibility, legacy worker-pipe cancellation semantics, handle inheritance and interactive native dialog behavior. Configuration echoes and passing fake tests are not proof of isolation. The legacy Python worker approval bridge must not become production authority; provider request binding belongs to the native host.

The public Windows download remains held. No website release or stable version is changed by this development branch.

Dispatch the existing `atlas-windows-validation.yml` workflow with ref `development/windows-native-approval`. That branch intentionally runs only the `native-development` fixture job; the default branch retains its restricted-package validation workflow.

The first development Windows run reached the C# compiler and found a test variable-shadowing error; no native fixtures ran. This revision fixes that error and adds provider-request deduplication and directly linked pending-grant revocation. Ten Python fixtures passed, while revised C# behavior awaits the next Windows run. No grant already delivered to a provider can be recalled with certainty.

The next Windows run compiled successfully but failed while deleting the disposable junction fixture, potentially masking its primary guard result. This revision reads back and removes only its own reparse tag before cleanup and preserves original failures. The exact previous cause is not claimed. The runner lacked 8.3 aliases; that case remains unverified.

[Native Windows CI 41238822580](https://github.com/jrish11/ATLAS/actions/runs/41238822580) passed the compiled custom native suite and ten Python fixtures at source `5bcf948`. The guard detected the tested in-place junction mutation. This revision additionally rechecks project identity immediately before queued thread, turn and approval writes; its new fixtures require Windows revalidation. This narrows a race without proving descriptor-bound isolation. No production code is wired to this prototype.

## Final native fixture result — 2026-10-31 UTC

[Windows run 41239065591](https://github.com/jrish11/ATLAS/actions/runs/41239065591) passed at exported code commit `97f78b7157f375a2a664ec30b0419c916cea5348`, corresponding to source `2430789e08911e135614d92012bb6c5bf3cc6bb5`. Ten Python protocol tests passed, and the custom C# executable compiled and passed its fake-child/provider, cancellation, revocation, duplicate-request and queued-project cases. The tested in-place junction mutation was detected by the guard. The volume did not provide 8.3 aliases, so that case is unverified. Seven independent static checks found no new blocker in the final dispatch-check diff.

These are synthetic protocol/native integration checks, not a live AI task or interactive UI test. No real account/provider, model/API request, native approval dialog, installation, permission change or app release occurred. The queued-project fixtures assert no forbidden output marker; a filler-write timeout could also prevent that marker, so these cases are not exhaustive race proof. Production Python, native entry points and the production project file remain byte-identical to restricted main. The development branch is not merged and its prototype has no production caller.

Before enabling Windows AI, implement and verify the trusted production broker, supported executable/protocol provenance, actual OS sandbox read/write/network denials, process/handle containment and interactive owner consent/cancellation. The retired worker-pipe experiment is not approval authority. Already-started writes/actions can have uncertain outcomes. Public Windows downloads remain held.

## Suspended containment development revision

This revision adds suspended Win32 creation, an explicit three-handle stdio inheritance list and job assignment before process resume. Independent static review found no new blocker in the bounded launch/cleanup change; actual Windows fixtures remain required. The updated queue test synchronizes writer arrival so a filler timeout cannot substitute for the intended race assertion.

The new native broker is immutable OFF, unwired and not part of the production application. Official CLI digest metadata and MXC probe scaffolding are present, but no actual official Windows binary bytes have been independently hashed or executed by this checkpoint. The default CI runs fake processes only; it does not invoke the opt-in Python sandbox probe, real accounts, a model or administrator setup. Parent-path/helper provenance, actual OS sandbox enforcement and interactive consent remain release gates.
