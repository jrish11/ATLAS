# Native approval development checkpoint

This branch exports the isolated native prototype from source `7f1f5eb75d27a8df270fc5afcd5f2ffb45604c28`. It is not imported by production. All Claude/Codex execution in the Windows preview remains disabled.

The manual 20-minute standard Windows CI compiles and runs custom C# and Python fixtures with fake processes and newly created runner-temporary directories. It does not open dialogs, read real accounts, request permissions, invoke Codex, spend API usage, publish artifacts or enable any AI gate.

Known review gates remain: actual provider/Windows sandbox enforcement, native executable provenance and protocol compatibility, duplicate provider-request identity handling, legacy worker-pipe cancellation semantics, handle inheritance and interactive native dialog behavior. Configuration echoes and passing fake tests are not proof of isolation. The legacy Python worker approval bridge must not become production authority; provider request binding belongs to the native host.

The public Windows download remains held. No website release or stable version is changed by this development branch.

Dispatch the existing `atlas-windows-validation.yml` workflow with ref `development/windows-native-approval`. That branch intentionally runs only the `native-development` fixture job; the default branch retains its restricted-package validation workflow.
