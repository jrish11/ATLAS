# Project checkpoint — 2026-10-31 UTC

This is an evidence and release-status checkpoint, not a new app release. No application, permission, account login, listener, signing identity or update feed is activated by it. The repository remains public at https://github.com/jrish11/ATLAS and preserves the upstream Atticus ancestry, MIT notices and Plip attribution. Local customized histories are exported through the documented sanitization process; personal companions and credentials are excluded.

## Published and draft artifacts

| Track | Exact source/export | Verified status |
| --- | --- | --- |
| Public Mac v3.6 | Source `ef7dfe5f92ba7a5e1d8ad824c1fa9772765f8d04`; tag `v3.6` | Latest published Mac prerelease. Apple Silicon/macOS 26+, ad-hoc signed, not notarized. Public ZIP SHA256 `2c1335d796fd53880dbb8dbcc57733493b39e952dd5b9626fcc2ab0adf5d259e`. It does not contain later First Light fixes. |
| First Light 1.1 RC2, build 3 | Source `c8de0c2d1f7a0b257d987dc98c6c829d7961e7a0`; export `13b3c59f9a1abb9d402f78e6ca76c75f98110ba6` | GitHub `v1.1-rc.2` remains a draft prerelease. Sanitized draft ZIP SHA256 `79648d553cb2152a8330f085e6b64cdd1111c6ca5e73f71b2962d2964aa3f974`. Separate private delivery is not a public release. Bundle identity `com.atticus.personal.dev`, short version 1.1.0, build 3, update epoch 1. |
| Windows restricted preview | Source `09583b54d2e00fdcfc9b17fc3ad03bd09b0938dc`; tested export `a29fb7b207636e7497ee7576481037c8bc714c56` | [CI 41237532147](https://github.com/jrish11/ATLAS/actions/runs/41237532147) passed 119 unit/fixture tests, zero skips, compilation, explicit dependency setup/cancellation and original/relocated Python/native self-tests. Final 350-file archive matches 349 manifest hashes plus the manifest. All AI and arbitrary saved-shell replay are disabled. No public Windows binary release. |
| Windows native development | Source `86f2541fcff3df61e6ff037328be431832bd160f`; tested export `9bbf120ad4b78b44d7e8c20c379b6ddca9e594ce`; documented head `45647fbf2331eb4d594339a3c13beb2c7500b73c` | [CI 41241040255](https://github.com/jrish11/ATLAS/actions/runs/41241040255) passed 10 Python fixtures, compiled fake native suite, four archive guards and actual official package/manifest/six-executable hashes. The real CLI stopped before boundary commands: `native MXC is unavailable on this executor`. Production broker stays OFF. |
| Signed updater development | Code export `b40a421233cf81866ea869e51cb53b9550e529fe`; source `fd241f8138a7a8852c65ce91729c6c51fddfb42f` | Verification/staging prototype only. 21 fixture tests use a fake signature callback; Swift CryptoKit adapter typechecked with an empty trust map. No production key, downloader or installer is configured. |

Historical public tags `v3` through `v3.6` remain intact. Only v3.5/v3.6 have public Mac binary assets; older private binaries are not republished. `v1.1-rc.1` and `v1.1-rc.2` remain drafts. There is no stable 1.1 production release, Windows AI download or signed automatic-update feed.

## Evidence limits and remaining gates

The RC2 packaging review recorded 162 focused checks, two guarded native-WebKit skips and 40 packaging checks. Both staged ZIPs passed relocation signature checks and 44 resource hashes; 34 Mach-O sections remained unchanged. This publisher did not independently rerun native self-tests because the app overrides temporary ATTICUS_DIR during bootstrap; source review confirmed the self-test paths return before protected activation. Native user interaction, physical MacBook behavior, voice/browser permissions and integrated account tasks are not established by those fixture counts. Runtime setup and authentication remain per-device; no credentials or browser sessions are transferred.

The Windows hosted context was Windows Server 2025 Datacenter 10.0.26100, image `windows-2025-vs2026` version `20261021.278.1`. Explicit MXC preparation failed, so project/sibling writes and loopback-denial commands did not execute. Do not weaken job containment or switch to legacy elevated/unelevated sandboxing to manufacture a pass. A compatible authorized environment is required for the same credential-free probe. Broader read/network denials, helper/load-graph trust, production broker wiring, real account execution and interactive native consent remain separate gates. Windows execution testing is paused at this checkpoint; no new feature tests are scheduled.

Phone/frontend work is a separate coordinated track. No phone service, private HTTPS route or listener was activated by this checkpoint. Owner approval for the target-host activation is pending. Frontend/interoperability evidence tracked by that coordinator is not represented as a newly published binary or independently rerun here.

## Updater status and exact future signing approval

Current updates remain manual. [Updater implementation and gates](https://github.com/jrish11/ATLAS/blob/development/signed-updater/scripts/personal-release/UPDATES.md) distinguish the staging verifier from an actual installer. Downloader restrictions, maintained installer integration, native update UI, durable receipts, crash reconciliation and real signature/update/cancel/rollback tests remain incomplete. Signing approval alone would not make this ready.

Before production signing, obtain explicit owner approval to create and use ONE persistent ATLAS Ed25519 release-signing identity in the owner's login Keychain, with an agreed secure-custody/backup plan. The owner must personally review any Keychain prompt. Independently verify its public fingerprint and embed only the public key. Never place the private key in Git, the application, release assets, logs or hosting. Sparkle's supported generator has not been run. [Sparkle documents this key setup](https://sparkle-project.org/documentation/). Developer ID certificates, Apple account access and notarization are separate distribution decisions requiring their own approval; none is implied by approving GitHub permissions or an update-signing key.

No model turns or paid inference requests were issued by the cited Windows tests. This is not a claim that the project's development allowance was measured as zero or that an exact weekly percentage is known. The separate foreground API test ledger remains with its assigned owner.

## Provenance

GitHub's Claude/Cursor contributor entries originate in upstream history: 44 Claude Opus 5.5 and 17 Cursor co-author trailers were found before the customization boundary. The 20 customized main-branch commits at the code checkpoint had zero new co-author trailers. Authentic upstream history and legal credit remain intact; new commits omit AI co-author trailers. [Attribution details](ATTRIBUTION.md).
