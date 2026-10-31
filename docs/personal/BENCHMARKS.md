> Historical development note. This may describe an earlier build. See the root README, CHANGELOG and RELEASES for current status.

# Atticus benchmark evidence

Environment: arm64 macOS 26.6.2; Codex CLI 0.155.1; upstream `287b2665f96febf581075a97d366dc5d620f3369`. These measurements do not demonstrate end-to-end task speed.

## Offline command routing

Run `PYTHONPYCACHEPREFIX=/tmp/atticus-bench-cache python3 tests/benchmark_routing.py --iterations 1000`. Both variants execute in one already-running Python process. The upstream fixture has no saved destination; the fork has an owner-confirmed fake destination and the actual browser action is mocked. Neither variant invokes a model or the network in this fixture.

| Fixture command | Upstream median / p95 | Fork median / p95 | Recognized out of 1,000, upstream / fork |
| --- | --- | --- | --- |
| Open Schoology | 0.0400 / 0.0500 ms | 0.0361 / 0.0464 ms | 0 / 1,000 |
| Go to Lovable | 0.0408 / 0.0517 ms | 0.0352 / 0.0470 ms | 0 / 1,000 |

This is a recognition-path comparison, not a comparison of equivalent completed tasks. The upstream might invoke a model after failing the fixture route; that fallback is deliberately not run or measured. Speech recognition, process startup, tab switching, network, page verification, click counts, cost and actual success are excluded.

## Native application lookup

Compile and run `tests/benchmark_native_lookup.swift` on macOS. One run outside the outer execution sandbox used `NSWorkspace.urlForApplication(withBundleIdentifier:)` 1,000 times per identifier:

| Identifier | Median / p95 | Found |
| --- | --- | --- |
| `com.apple.Safari` | 0.0018 / 0.0023 ms | 1,000 / 1,000 |
| `md.obsidian` | 0.0022 / 0.0051 ms | 1,000 / 1,000 |
| `com.openai.codex` | 0.0018 / 0.0024 ms | 1,000 / 1,000 |

These are warm, in-process Launch Services lookups, not launch or response times. Inside the outer sandbox the same lookup returned no applications, so those values are not used as a valid application-discovery baseline.

## Restricted sandbox fixture

`python3 tests/validate_codex_sandbox.py` creates a disposable home and named Codex permission profile, then tests only fixture files. On this Mac, running outside the outer execution sandbox with CLI 0.155.1: workspace read/write were allowed; sibling read/write, an escaping symlink read, fixture Codex configuration write and loopback connection were denied. The outer sandbox itself prevented nested sandbox creation. The separate `tests/validate_codex_appserver.py` fixture verified the adapter-created named profile and workspace roots through app-server, observed the same boundary results, hid a dummy environment token, and verified six initially enabled system skills were disabled after restart. Neither fixture starts a model turn or uses credentials. These disposable fixtures do not prove that a real project or authenticated task has been validated.

## Acceptance scenarios still unrun

| Scenario | Status and reason |
| --- | --- |
| Open Schoology | Routing fixture only; real Safari Automation and page verification not tested. |
| Switch to an existing Schoology tab | Script syntax and mocked outcome only; real browser permission test not run. |
| Open Lovable | Routing fixture only; real browser task not run. |
| Open a specific Lovable project | Editing-project URL not established. |
| Launch Obsidian | Native bundle lookup only; launch and interface not tested. |
| Find an Obsidian note | No real note search test or provider transmission performed. |
| Start a Codex background task | Live launch remains disabled pending app-server isolation and approval integration. |
| Resume an earlier task | Thread protocol and restart behavior are fixture-tested; no live task exists. |
| Execute a learned workflow | Python fixtures only; no real-app replay or approval flow tested. |
| Recover when a website changes | Not tested against a real website. |
| Complete a multi-step browser task | Not tested; browser permissions and authenticated flow remain unverified. |
| Complete several independent tasks concurrently | Existing queue and adapter fixtures only; no live multi-agent task run. |

No real voice latency, time to first action, end-to-end completion time, actual clicks, model call counts, API cost, real success rate, recovery time or resource usage has been measured. Targets must be set only after a reliable original-versus-fork live baseline is available.

## Resident destination lookup

`python3 tests/benchmark_resident.py` compares a missing synthetic destination in a minimal freshly started Python interpreter with the same personal registry lookup through the already-running Agents supervisor over its private stdin/stdout pipe. On this Mac, one run measured cold import and lookup (40 requests) **28.536 ms median / 29.346 ms p95**, versus resident IPC and lookup (400 requests) **0.030 ms median / 0.040 ms p95**. Both returned no match. No browser actions, model calls, network, speech or UI were involved. The cold comparator imports only `personal_commands`; it is not a measurement of the original full `--fast` process, so these numbers are not an upstream-versus-fork end-to-end comparison. The supervisor startup cost is excluded.

The confirmed whole-request path now uses the resident supervisor for saved destinations when available. Unknown requests fall back to the existing path. Generic live partial-transcript `--fast` requests still launch Python, and existing speech speculation remains in place. Neither the new native UI route nor real Safari actions have been exercised end to end.
