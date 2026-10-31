# Native approval development checkpoint

This branch exports the isolated native prototype from source `ee501f2fac4601ba417ac0e8f599645ff2b96b81`. It is not imported by production. All Claude/Codex execution in the Windows preview remains disabled.

The manual 20-minute standard Windows CI compiles and runs custom C# and Python fixtures with fake processes and newly created runner-temporary directories. It does not open dialogs, read real accounts, request permissions, invoke Codex, spend API usage, publish artifacts or enable any AI gate.

Known review gates remain: actual provider/Windows sandbox enforcement, native executable provenance and protocol compatibility, legacy worker-pipe cancellation semantics, handle inheritance and interactive native dialog behavior. Configuration echoes and passing fake tests are not proof of isolation. The legacy Python worker approval bridge must not become production authority; provider request binding belongs to the native host.

The public Windows download remains held. No website release or stable version is changed by this development branch.

Dispatch the existing `atlas-windows-validation.yml` workflow with ref `development/windows-native-approval`. That branch intentionally runs only the `native-development` fixture job; the default branch retains its restricted-package validation workflow.

The first development Windows run reached the C# compiler and found a test variable-shadowing error; no native fixtures ran. This revision fixes that error and adds provider-request deduplication and directly linked pending-grant revocation. Ten Python fixtures passed, while revised C# behavior awaits the next Windows run. No grant already delivered to a provider can be recalled with certainty.

The next Windows run compiled successfully but failed while deleting the disposable junction fixture, potentially masking its primary guard result. This revision reads back and removes only its own reparse tag before cleanup and preserves original failures. The exact previous cause is not claimed. The runner lacked 8.3 aliases; that case remains unverified.

[Native Windows CI41238822580](https://github.com/jrish11/ATLAS/actions/runs/41238822580) passed the compiled custom native suite and ten Python fixtures at source5bcf948. The guard detected the tested in-place junction mutation. This revision additionally rechecks project identity immediately before queued thread, turn and approval writes; its new fixtures require Windows revalidation. This narrows a race without proving descriptor-bound isolation. No production code is wired to this prototype.
