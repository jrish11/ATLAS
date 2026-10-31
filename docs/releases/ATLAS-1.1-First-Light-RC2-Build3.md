# ATLAS 1.1 First Light - RC2 / Build 3

PRIVATE DIAGNOSTIC RELEASE CANDIDATE. NOT PRODUCTION-READY.

This combined candidate contains the request-ID repair, explicit Codex/Claude Code selection, background/appearance controls and reviewed companion code. Phone/browser interoperability, live owner activation and integrated account tasks are still unverified. Do not treat included phone controls as a ready connection. Leave phone/remote access OFF until its separate owner-supervised activation and interoperability checks are complete. No paired keys, credentials or browser sessions are included.

The website's primary download is unchanged. Existing public3.x preview history is retained. This package is RC2 with INTERNAL BUILD3, not a verified stable1.1 release.

## Update without redoing setup

Quit the customized ATLAS copy, back up only its app bundle, then replace ONLY that customized copy with the included ATLAS.app. Do not overwrite official Atticus or the unrelated older ATLAS prototype. Never run old and new copies together. Keep memory, settings, runtime, Keychain and vault data intact. macOS may require your review of this changed ad-hoc signature.

About shows ATLAS1.1 / First Light; it does not display Build3. This package filename and Contents/Resources/release-manifest.json identify the reviewed source. Finder's app metadata is version1.1.0, internal bundle build3, update epoch1. These internal values advance from the previews while display branding changes to1.1. The app identifier/profile/runtime/Keychain namespaces remain those of the customized fork. No automatic updater is active.

## First owner check: Cancel without a model turn

1. Create a NEW empty local folder named ATLAS Cancel Test on your Mac.
2. Open Agents -> New agent task...; select Codex (existing ChatGPT account).
3. Use Choose a different project... to choose that empty folder. Enter: Create result.txt containing READY
4. Click the FORM'S Start agent task ONCE. Verify that the separate native Start this Codex task? dialog appears with the exact project/task.
5. Click native Cancel, NOT Start Codex task. Check no agent started and no result.txt was created. The form should report that the task was not started and unlock.
6. Report actual results, package/build and exact errors. Do not repeat pending or uncertain requests.

This checks the reported UI exception and cancellation path; it does not verify a live Codex task. The UUID fallback requires cryptographic getRandomValues when randomUUID is absent and fails without dispatch if secure randomness is unavailable. No weak random fallback is used.

## Account and action boundaries

Foreground OpenAI uses the per-device Keychain-backed Terra6.1 API configuration. Codex uses its separate existing ChatGPT login; tested CLI protocol gate0.155.1, account default model, no foreground-key fallback. Subscription and API billing are separate. Claude Code is an explicit separate provider using its own installed CLI/account and restricted scratch workspace; Safe mode/sandbox are required and inherited personal tools disabled. Live provider behavior remains unverified for this combined app.

Review native scope and permission expansion. A completed model turn is not independent proof of correct files. Stop cannot undo dispatched effects. Unknown/restart/cancel-review outcomes require inspection before retry. Untrusted pages and notes cannot authorize scope changes. Experimental Autopilot remains narrow and OFF after restart; it is not unrestricted computer control.

## Per-device dependencies and permissions

Apple Silicon arm64, macOS26+, working /usr/bin/python3, Node22.19+/npm and an explicitly installed Pi runtime are required. If your existing runtime validates, do not redo setup. Otherwise use Set up Atticus runtime... in Intelligence/provider setup, review Open Setup and Terminal's download prompt. Fallback: Show Package Contents -> Contents/Resources/Setup/Setup.command. Node: https://nodejs.org/en/download . Existing incomplete runtime folders are not silently overwritten.

Codex setup: https://developers.openai.com/codex/cli/ . Its login is separate from the foreground API key. No credential transfer or automatic login grant is included. Settings, voice and the compact floating interface are retained; wake listening remains your existing choice, not automatically enabled.

The app is ad-hoc signed, NOT Developer ID signed or notarized. Do not disable Gatekeeper/SIP, remove quarantine or bypass security warnings. Review and report blocks yourself. Grant only intended Microphone, Accessibility, specific-app Automation, requested Speech Recognition or implemented capture permission. Routine Full Disk Access/admin is not required. Permissions do not make an unfinished feature complete.

## Evidence and limits

Frozen source: c8de0c2d1f7a0b257d987dc98c6c829d7961e7a0.
Input executable SHA256: ad39a537ec31c5c15fb6ef53008519e36e18b1435f11d9b12c5e83d807970db5.
Independent regression suite:162 checks passed,0 failures,2 guarded native WebKit checks skipped.40 packaging checks passed. The coordinator's separate bounded combined-code review reported95 passing checks and producer native selftests/signature checks. Packaging independently verifies resource/source identity, both MIT notices, signature, relocation, import closure and privacy. These are not actual native UI, phone pairing, voice, browser or live model acceptance tests.

The selftest startup overrides an externally supplied ATTICUS_DIR. Independent packaging therefore does NOT claim a temporary-profile native selftest run; those native modes were not rerun as part of this packaging pass. Source review shows they exit before listener, owner/pairing/provider or actual Keychain activation. No normal app launch, capture, real pairing, OS grant or model/API call occurred during independent packaging. Binary/resource hashes do not establish a fully reproducible build.

No ready phone connection, universal background operation, full computer-control completion, Obsidian/iCloud conflict guarantee, signed automatic updater or Windows parity is claimed. The reviewed companion code is present for staged testing only. Website/production promotion remains blocked on its live checks and explicit activation approval.

## Rollback and attribution

Quit this candidate and restore ONLY the backed-up customized app bundle. Leave profile/runtime/Keychain/vault data intact. App rollback does not undo completed external work or confirmed memory changes. Required Atticus and Plip MIT notices are in Contents/Resources/Licenses. Source/provenance: https://github.com/jrish11/ATLAS . Authentic upstream contributor history is retained.
