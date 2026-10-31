# Codex Agents integration: owner/VM checklist

This component is not in the previously delivered ZIP. It does not enable live dispatch by itself. The backend patch is a proposal for the sole source writer to review and integrate.

Automated evidence is JavaScript/controller execution on a synthetic DOM plus real Python registry behavior with fake providers. No native rendering or microphone use is claimed. The repository host guard blocks compiled WebKit and voice fixtures on the owner's Mac; do not set bypass flags on that Mac to make a test appear passed.

In the project's actual isolated VM test environment, run the native approval fixture and the production-guard voice fixture through the project's test runner. The latter compiles only Foundation and fake permission/device types; it contains no AVFoundation/AppKit import, audio capture or provider request. Swift compilation was verified on the host, but binary execution was skipped by the host guard.

For a separately coordinated owner check, have the source writer provide an explicit synthetic-provider test build. Normal app startup can request microphone/speech permissions and start its supervisor; do not use it as an unannounced substitute for a test harness. Leave real keys and personal projects out of the fixture.

1. Open the existing Agents window. Choose **New Codex task…**. Closing the form must dispatch nothing. Relative paths, empty instructions and an unchecked project confirmation must dispatch nothing.
2. Enter the disposable fixture's absolute path, a harmless task and the scope confirmation. Start once, then double-click. Verify one recorded task and one dispatch receipt. The form says request sent, never success.
3. Show a synthetic approval card. Check **Allow**, **Don’t Allow** and stale/repeated clicks in separate fixture runs; only the matching pending token may be consumed once. No real permission expansion is allowed by the test.
4. Stop a synthetic running task. Verify **Cancellation requested; no interruption has been confirmed.** until its terminal receipt arrives. Check interrupted, completed-before-cancel and unknown outcomes. A cancellation-review requirement must disable continuation.
5. Inspect the synthetic project, use **Review cancellation…**, then enter a follow-up instruction and choose **Continue scoped task**. Verify the existing agent/thread scope is retained, and repeated clicks dispatch once.
6. Restart the synthetic supervisor with a persisted request ID and a pending cancellation. Verify no automatic redispatch. A repeated request ID returns the recorded row; conflicting payloads are rejected.
7. If no task record acknowledges a submission, inspect Agents/project first. The explicit review checkbox can unlock the form; unlocking itself must never resend a task.

Only after this scoped UI verification should the source writer enable the proposed narrow readiness path. It accepts only verified CLI 0.155.1 on macOS and an existing confirmed project. API mode, unknown versions and protected roots remain blocked. The adapter must still independently verify existing ChatGPT account/default model and effective disabled MCP/apps/hooks/skills, restricted reads/writes and no network before a model turn. Account model listing is not entitlement proof; unsupported account models fail closed, with no API fallback.

# Separate speech improvement proposal (no Swift edit in this component)

`prepareSpeech()` currently uses `try?` for asset-installation request/download and clears `preparingSpeech` without retaining the failure. Add a bounded, non-secret setup error state on MainActor and display a **Retry speech setup** action in existing General settings. A failed asset install should not claim readiness or start an infinite retry; typed input must remain available. Retry only after owner action, preserve stale generation checks, and test download failure, unavailable format, cancellation and successful retry with fake asset providers. Do not request microphone or speech permissions merely to render this error.
