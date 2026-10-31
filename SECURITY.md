# Security policy

## Release status and support

ATLAS is an experimental customized fork of Atticus. Public3.x releases are
previews; ATLAS1.1 First Light is a release candidate until its documented gates
pass. No current production-security certification, response deadline or bounty
program is promised. Report a finding against the exact source commit, artifact
version, operating system and relevant configuration. Maintainer triage is best
effort; check the current README/release notes for supported or blocked features.

## Reporting a vulnerability

Private vulnerability reporting is enabled for this repository. Use
[Report a vulnerability privately](https://github.com/jrish11/ATLAS/security/advisories/new)
in GitHub. Do not post exploit details, keys, account tokens, personal notes,
browser sessions or sensitive logs in a public issue. Report only synthetic or
redacted reproductions through the private channel.

When reporting through that enabled private channel, provide a minimal synthetic
reproduction, expected versus observed behavior, affected version/commit, and
the scope of potential impact. Redact secrets and personal data. Never test on
another person's device/account or on private records without authorization.

## Areas of interest

Approval forgery/replay, prompt-injection authority changes, sandbox escapes,
untrusted browser/note instructions, memory or export leaks, insecure provider
authentication, hostile update archives, rollback/crash duplication and pairing
revocation are relevant. A passing mock or model completion is not proof of a
secure real-world result. See release evidence and documented threat limits.

## Scope and disclosure

This policy applies to this ATLAS repository and its own artifacts. Upstream
Atticus/Plip, dependencies and hosting/providers have separate maintainers and
policies. Coordinate public disclosure with the maintainer when a private report
exists; no fixed embargo or guaranteed response timeline is imposed here.

Never submit credentials with a report. No approval bypass, automatic permission
grant or production self-modification is authorized by a vulnerability report.
