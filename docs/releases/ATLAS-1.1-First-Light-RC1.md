# ATLAS 1.1 - First Light - RC1

RELEASE CANDIDATE FOR SUPERVISED TESTING. NOT PRODUCTION-READY.

This candidate contains the Codex Start request-ID repair, explicit Codex/Claude Code choice, Settings appearance and covered background safeguards. The website's primary download remains the existing preview. Earlier public 3.x tags/releases remain historical previews.

## Update without resetting setup

1. Quit your customized ATLAS copy and back up its app bundle separately.
2. Unzip and replace ONLY that customized copy with ATLAS.app. Do not overwrite official Atticus or the unrelated old ATLAS prototype. Never run two copies together.
3. Keep memory, settings, runtime, Keychain and Obsidian data intact. No profile/key reset is needed. Review any changed-signature permission prompt yourself.
4. Open the new copy. About should show ATLAS 1.1 / First Light and upstream Atticus 1.5.4 separately. Internal bundle build advances from 1 to 2. The lower display label is deliberate branding; no signed updater is enabled.
5. Perform the Cancel-only test below before authorizing a live model task.

## FIRST TEST: Cancel at native confirmation

This checks the reported UI exception without spending a model turn.

1. Create a NEW empty local folder named ATLAS Cancel Test on your Mac.
2. Open Agents -> New agent task... and select Codex (existing ChatGPT account).
3. Use Choose a different project... to select that empty folder. Enter: Create result.txt containing READY
4. Click the form's Start agent task ONCE. It should open the separate native Start this Codex task? dialog. Verify the exact folder/task shown.
5. Click native Cancel, NOT Start Codex task. Check that no agent started and no result.txt exists. The form should report that the task was not started and unlock.
6. Report the app version, actual outcome and exact error if any. Do not repeatedly submit duplicates or authorize a task merely to dismiss an error.

The reported exception was crypto.randomUUID being unavailable in some file-origin WebKit contexts. This candidate falls back ONLY to cryptographic getRandomValues. Missing secure randomness fails without dispatch. Actual JavaScript controller fixtures cover this fallback, duplicate submission, correlated errors/cancellation and Continue. Actual on-device WebKit still needs the supervised check. Cancel-only success does NOT prove that a real Codex task works.

## Separate accounts

Foreground OpenAI uses your saved per-device Keychain API key and Terra 6.1 configuration. Codex uses its supported existing ChatGPT login, separately from API billing. Its tested protocol gate accepts Codex CLI 0.155.1 only: https://developers.openai.com/codex/cli/ . No login token/key/session is included or transferred.

Claude Code is an explicit separate option using its own installed CLI/login, Sonnet and a private scratch workspace. Safe mode is required. Inherited personal tools are disabled for this entry; its sandbox cannot opt into unsandboxed commands. Sensitive actions retain approvals. This account path has synthetic tests, not new live-provider proof.

A sent request or completed model turn does not verify correct work. Inspect real files/results before marking work verified. Stop cannot undo dispatched effects. Unknown/cancel-review outcomes need inspection before retry.

## Retained controls

Settings appearance offers System/Light/Dark for Settings only; compact chat stays dark. Do not interrupt my work defaults ON for covered model app/saved-page/media actions. Explicit owner opens, independent routes and apps can still focus. This is not universal background execution. Autopilot remains experimental and OFF after restart, at most one app/one confirmed HTTPS destination for ten minutes; sensitive approvals remain.

Confirmed deterministic commands and memory are retained. Atlas is the wake name; listening remains your existing choice. Local folder previews are bounded and are not automatically sent to a model. Full computer-control completion, Obsidian/iCloud sync and every inherited feature are not release-verified.

## Requirements and security

Apple Silicon arm64, macOS 26+, working /usr/bin/python3, and an explicitly installed per-device Pi runtime using Node 22.19+ and npm. If your existing runtime validates, do not redo setup. If needed choose Set up Atticus runtime... in Intelligence/provider setup, then review Open Setup and Terminal's download prompt. Fallback: Show Package Contents -> Contents/Resources/Setup/Setup.command . Node: https://nodejs.org/en/download . Incomplete runtime directories are not silently overwritten.

The app is ad-hoc signed, not Developer ID signed or notarized. Do not disable Gatekeeper/SIP or strip quarantine. Review security warnings yourself. Grant only intended permissions: Microphone for voice, Accessibility for implemented control, Automation only for an actually requested app, Speech Recognition only if requested, recording permission only for an implemented capture need. Routine Full Disk Access/admin is not required. Permission grants do not implement missing features.

## Evidence and limits

Source freeze: a9b66b5069ab2d0a02335edd6f63ddf120e99f87. Its final commit adds only the VM-guarded UUID test after the branding build. 161 focused checks passed, 0 failed, 2 native WebKit checks skipped under host restriction. 17 packaging checks passed. Relocated ZIPs are separately checked for signatures, both native self-tests, resource hashes, privacy and licenses. Hash/resource equality does not independently prove a reproducible build.

Native Start/Continue, live account approval/cancel/restart, real MacBook voice/browser/OS dialogs and Windows interaction remain unverified. NO phone control or ready phone pairing is included. NO automatic update feed/installer is enabled. No new model/API calls were made for this review or package.

## Rollback and attribution

Quit the candidate and restore ONLY the backed-up customized app bundle. Preserve profile/runtime/Keychain/vault data. Rollback does not undo external work or confirmed memory edits.

ATLAS is a customized Atticus fork. Full required Atticus MIT (Copyright 2026 SaarthurR) and Plip MIT (Copyright 2026 Hussain) notices are in Contents/Resources/Licenses. Source: https://github.com/jrish11/ATLAS . Authentic upstream history remains; development tools are documented without fabricated authors.
