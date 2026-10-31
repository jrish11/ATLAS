# Code-scanning review, 2026-10-31

Baseline: public `main` at `51f5cffe24a56297142b385f0a3534e5bc8673f2`.
This is a finding-by-finding review, not a claim that the repository is secure.
Do not close a finding solely because a related change appears in a draft PR.

An independent review examined every reported thread flow in baseline Python
SARIF analysis `2069506111`. For alerts 7–9, 11–13, and 15–18, its modeled
Keychain source crosses separate calls to `pref`: the actual Keychain branch
only runs for `apiKey`, whereas the reported sink paths call it for other
literal keys. For 17–18 the trace also conflates the routine model field with
separate request evidence. Synthetic fake-Keychain tests supported that narrow
conclusion for both source copies. This does not rule out secrets typed by an
owner or other sensitive content in the same outputs or plaintext files, and
does not establish that unrelated data flows are safe. Those findings remain
open while the actual privacy boundary and request retention are reviewed.

| Alert | Location and assessment | Disposition |
| --- | --- | --- |
| 1 | Windows settings integration URL was placed into an anchor. A configured non-HTTP URL could become a script URL. | Draft fix restricts scheme and destination origin; scanner and review pending. |
| 2 | Windows JavaScript syntax-test regex only recognized lowercase script tags. This is test fixture parsing, not application sanitization. | Draft fix; scanner pending. |
| 3 | Desktop JavaScript syntax-test regex, same test-only limitation as 2. | Draft fix; scanner pending. |
| 4 | Remote experiment JavaScript syntax-test regex, same test-only limitation as 2. | Draft fix; scanner pending. |
| 5 | Remote experiment onboarding test removes script tags using a case-sensitive regex. It operates on the repository's test fixture, not untrusted user content. | Draft fix; scanner pending. |
| 6 | Desktop onboarding test, same test-only limitation as 5. | Draft fix; scanner pending. |
| 7 | Desktop `say` writes assistant output to stdout. The native app normally connects stdout to a pipe; a direct CLI caller or redirect can receive that output. | Unresolved: trace the reported secret flow and establish a safe output contract; do not blindly redact normal answers. |
| 8 | Desktop `Agents` default emitter serializes events to stdout, normally a native process pipe. Agent events can contain private user content. | Unresolved: trace the reported flow and access boundary. |
| 9 | Remote experiment copy of 7. | Unresolved; same assessment. |
| 10 | Desktop `meeting_live` non-Claude branch prints only a fixed error and `client().title()`. `client()` returns only `claude`, `devin`, or `pi`, even for an unrecognized preference. No input, key, or meeting content reaches this particular sink. | Independently reviewed and dismissed as a false positive for this specific line. |
| 11 | Desktop `--feedback` serializes the feedback response over stdout. | Unresolved: inspect the input and downstream pipe; no blanket suppression. |
| 12 | Desktop `--meeting-gather` serializes meeting data over stdout, normally to its requesting native UI. | Unresolved: inspect privacy and IPC exposure. |
| 13 | Remote experiment copy of 8. | Unresolved; same assessment. |
| 14 | Remote experiment copy of 10. Its `client()` has the same three-value allowlist. | Independently reviewed and dismissed as a false positive for this specific line. |
| 15 | Remote experiment copy of 11. | Unresolved; same assessment. |
| 16 | Remote experiment copy of 12. | Unresolved; same assessment. |
| 17 | Desktop agent request evidence is saved as plaintext. It is later read by approval, focus, and learning code. The previous create-then-chmod sequence also briefly allowed broader permissions. | Draft atomic mode-0600 write removes that window, but data remains plaintext and lifecycle/architecture review is still required. |
| 18 | Remote experiment copy of 17. | Draft permission hardening only; plaintext remains unresolved. |
| 19 | `platforms/windows/notices/python-native-3.13.17/SQLite-official-copyright.html` is a preserved third-party notice. Its script assigns `data-href` from an element named `mtimelink`, but the shipped static document contains no such element or `data-href` attribute. | Independently reviewed and dismissed as a false positive for this static file; preserve the upstream notice and reassess if embedded in an untrusted DOM. |

The CodeQL C/C++ job in run 41236304698 failed because it found no source files;
it did not provide C/C++ coverage. The current configured language list should
be reviewed against actual maintained source, without disabling meaningful scans.
The Windows job in the same historical run failed in Codex provider tests,
including a hard-coded `/tmp` path and fixture skill-path verification. Commit
`ea1b233` corrected those fixture paths, and Windows runs 41237172660 and
41237532147 passed. The latter commit is an ancestor of this baseline, with no
intervening Windows source, workflow, or staging changes. A separate Windows
run is still required for the settings change in this security branch.
