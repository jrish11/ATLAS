> DEVELOPMENT RC2 / INTERNAL BUILD3: frozen combined sourcec8de0c2.162 focused checks passed with2 guarded native WebKit skips;40 packaging checks passed. Phone interoperation, explicit activation and live owner checks remain unverified; no production readiness or website promotion is claimed. See [private-test candidate limits](docs/releases/ATLAS-1.1-First-Light-RC2-Build3.md). The public primary download remains v3.6.

# ATLAS

A customized fork of [Atticus for macOS](https://github.com/SaarthurR/atticus-mac), retaining its compact floating interface, menu bar, voice/typed interaction and existing architecture. ATLAS is not the unrelated earlier prototype bearing the same name.

**Current Mac preview: v3.6. Last updated: 2026-10-31 UTC.** Exact source: `ef7dfe5f92ba7a5e1d8ad824c1fa9772765f8d04`. Public source repository: [jrish11/ATLAS](https://github.com/jrish11/ATLAS). The owner approved public publication; this repository contains sanitized exports rather than the raw local customized commit graph. See [release metadata](RELEASE-METADATA.json), [changelog](CHANGELOG.md), [release inventory](RELEASES.md) and [build instructions](docs/BUILD.md).

## Next release line: First Light (draft)

**ATLAS1.1 “First Light” is a release candidate, not production-ready.** The existing public3.x previews/tags remain part of the history; current download below remains v3.6. See [First Light gates and migration plan](docs/releases/ATLAS-1.1-First-Light-DRAFT.md). The reported embedded-WebKit Start task exception has a fix under review; v3.6 does not include it. Phone pairing and integrated live Codex are not yet release-verified.

## Download and versions

[Download the experimental macOS v3.6 ZIP](https://github.com/jrish11/ATLAS/releases/download/v3.6/ATLAS-v3.6-macOS-arm64-PUBLIC.zip) · [All documented prereleases](https://github.com/jrish11/ATLAS/releases) · [Source tags](https://github.com/jrish11/ATLAS/tags). Apple Silicon/macOS 26+, ad-hoc signed and not notarized; read setup requirements and limitations first. Windows remains source-only. Historical prereleases expose source, not private older binaries.

## New in v3.6

- Settings appearance: System, Light or Dark for Settings only; the original compact chat remains dark.
- Do not interrupt my work defaults on and pauses covered model foreground actions. Named AX presses and basic volume/player transport may work without focus. Explicit owner opens and other routes can still focus; this is not a universal guarantee. Queued covered actions recheck setting changes; stale click scope is invalidated.
- Source code in About opens this verified repository. Settings, runtime, profile and Keychain identities are preserved.
- 139 focused synthetic tests and 17 packaging tests passed; both relocated ZIPs passed signatures, two native self-test modes and 37 resource hashes. Native interactive appearance/background behavior remains unverified.

## Current behavior

- Known confirmed destinations and supported exact media commands can use deterministic local routing without model planning. Real voice-to-action latency and general browser success have not been established.
- Foreground OpenAI uses a locally entered Keychain-backed API key with Terra 6.1 configuration. Codex uses its supported existing ChatGPT account separately; subscription usage is not API billing.
- Experimental Codex jobs use the existing durable Agents registry. Native task/project approval, bounded account/configuration preflight, correlated progress, cancellation outcomes and restart review remain required. Natural-language scope grammar is intentionally conservative. A clear new task gets an exclusive workspace; uncertain existing-project references ask for a folder.
- Persistent memory extends existing structured records, including confirmed destinations, corrections and workflow records. Personal context sharing is off by default, reviewed for exact selected facts/model, and session-bound. Local folder preview is limited to explicitly approved top-level text/Markdown files; it is not arbitrary file access or automatic model sharing.
- Optional Obsidian logging uses actual owner-verified outcomes, exclusions and create-if-absent notes. Real sync conflicts and the full voice retrieval flow are not established.
- Experimental Autopilot grants at most one installed-app open/focus target and one confirmed HTTPS Safari destination for ten minutes. It starts off after restart. The native screen displays scope and requires confirmation. Sensitive and other actions retain approvals. Stop cannot undo dispatched actions.
- Exact volume, pause/resume, Music quit and exact Spotify track-link requests avoid repeated model control loops. A named song currently opens search for manual selection; it is not verified named-song playback. Deny ends the current foreground request's approval channel.
- Atlas is the default wake phrase. Exact legacy Atticus migrates; other custom names and the existing listening switch are preserved. Listening defaults off. Actual wake audio on another Mac remains unverified.

## Platform status

| Track | Status |
| --- | --- |
| Mac v3.6 | Apple Silicon / macOS 26+ experimental preview; ad-hoc signed, not Developer ID signed or notarized. External per-device Python/Node/Pi setup is required. |
| Windows | Separate source-only development at `418df8f59f776dc24ada02afd504603d7a7ffa7c`. No Windows binary or native Windows runtime verification. |
| Remote / phone | Separate experimental source at `bd86e865b4a8234284c3cb53ecf9e40fd696368c`; not in the delivered v3.6 app. Off-by-default synthetic integration only; no actual phone/proxy/live Codex validation. |
| Phone frontend / PWA | Not a ready released product. No independently verified PWA release is represented here. |

Native MacBook voice, browser sessions, interactive approvals/Autopilot and integrated live Codex remain unverified. Do not interpret a passing mock or completed model turn as proof that work was correct. No unrestricted computer control, credential/session transfer, automatic permission grant or automatic update feed is provided.

## Safety and privacy

No personal profile, private school/project destinations, keys, logs or vault contents belong in this repository. The separately delivered private optional profile is deliberately excluded. Keys remain local in Keychain. Untrusted sites, notes and model output cannot grant authority. Read the exact native scope before approval, deny unexpected expansion and inspect uncertain/canceled results before retrying. Do not disable Gatekeeper, SIP, quarantine or other security controls to run this preview.

This repository uses sanitized snapshot commits/tags, not rewritten original development history. Original local commits contain non-noreply author metadata and some personal references and are not automatically safe to publish. Clean upstream ancestry is retained in Git; see [publication plan](docs/PUBLICATION-PLAN.md). Historical development notes under `docs/personal` may be stale; this README and versioned release records take precedence.

## Validation

For v3.6: 139 focused synthetic regression tests and 17 packaging tests passed. Prior v3.5 included 102 focused checks and 13 additional bounded intent probes. Both sanitized ZIP variants passed relocated signatures, native self-tests and 37 resource hashes. Native self-tests do not establish microphone/audio/UI behavior. See [test evidence](docs/TEST-EVIDENCE.md). Run the bounded offline checks with `bash scripts/run-offline-checks.sh`; no model/provider request is required.

## Repository security and contributor history

[Security policy and private reporting](SECURITY.md) describes safe reporting. Private vulnerability reporting and Dependabot alerts are enabled. CodeQL initial validation completed successfully for Python, JavaScript/TypeScript and C# on standard runners ([run](https://github.com/jrish11/ATLAS/actions/runs/41232314897), source e1962a6). Swift coverage and full security assurance are not claimed. Secret scanning/push protection remain enabled; automatic dependency fixes remain disabled.

The GitHub Compare & pull request banners are development-branch notices. Claude/Cursor contributor avatars originate in the retained upstream history; new ATLAS exports have no coauthor trailers. See [maintainer/tooling and provenance](docs/ATTRIBUTION.md).

## Attribution

[Atticus](https://github.com/SaarthurR/atticus-mac): MIT, Copyright (c) 2026 SaarthurR. [Plip](https://github.com/hussainn7/plip-oss): MIT, Copyright (c) 2026 Hussain. Preserve [LICENSE](LICENSE) and [LICENSE-Plip](LICENSE-Plip). The upstream README also credits [Cua Driver](https://github.com/trycua/cua) ideas for background key authentication/menu shortcuts. This fork is not an endorsement by those projects. The original README is retained under `docs/UPSTREAM-README.md`.
