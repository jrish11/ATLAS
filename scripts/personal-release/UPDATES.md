# Signed update implementation checkpoint

This component is development-only. Public ATLAS v3.6 and the separately
delivered First Light RC builds still use manual replacement. No updater,
signing key, feed or automatic installation has been enabled by this component.

## Existing implementation and reuse

The upstream `Updater` in `Atticus.swift` fetches its source checkout, performs
a fast-forward pull, runs `build.sh`, then restarts when idle. That build script
installs an app, handles a local signing identity and writes startup integration.
It is not a portable binary updater. The customized bundle's `manualUpdates`
guard prevents that path from running and must remain until a replacement is
fully verified. Do not point this shell updater at the new repository.

Keep the compact UI and existing busy/agent/voice/meeting/settings checks, status
display and owner-triggered update action. Replace only the download/verification
and installation backend. Maintain bundle ID `com.atticus.personal.dev`, the
existing profile/runtime/Keychain namespaces and normal OS security checks.
Never use an update to migrate credentials or copy browser sessions.

For the production installer prefer the maintained
[Sparkle framework](https://sparkle-project.org/documentation/), including its
Ed25519 archive validation and signed-feed/release-note support where supported
by the selected, tested version. This avoids inventing a privileged installer.
Its framework and helpers need verified provenance, licenses and the chosen
macOS signing setup. Do not download or integrate a moving unverified binary.

`update_verify.py` is a separate release-validation/staging prototype, not a
Sparkle feed implementation or an installation engine. It tests the repository,
identity/version/channel/expiry/sequence constraints and hostile archives before
staging. `UpdateTrust.swift` supplies the shape of a CryptoKit verification
adapter with an intentionally EMPTY embedded key map. No valid release can pass
the default trust configuration. It does not generate, import, read or store
private keys. A fixture verifier is never an acceptable production substitute.

## Verification contract

Native trusted code owns all update state. WebKit/model text may request to
show the update screen but cannot choose a feed, public key, destination,
verifier, sequence receipt, executable or approval result.

1. An unsigned GitHub API response may announce a candidate only. Never treat
   HTTPS, a GitHub checksum or a key served by that same feed as independent
   publisher authentication.
2. Verify an exact-byte detached signature using an independently provisioned,
   embedded trust root before parsing fields that grant authority. Reject
   unsupported fields, duplicate JSON keys, oversized data, invalid signatures,
   unknown keys and clock/expiry problems. A signature covers the release notes,
   artifact URL, digest, byte length, version, channel and platform constraints.
3. Stable and preview channels are explicit. These current v3.x releases are
   prereleases; they must not silently become stable candidates. Compare product
   versions and a monotonic release sequence separately from upstream's dated
   bundle version. A local app-owned trusted receipt prevents rollback/replay;
   failure to read or persist it blocks installation rather than resetting it.
   The development protocol is schema2: signed `update_epoch`, globally
   increasing `build`, and globally increasing feed `sequence` are distinct from
   the product's display version. A signed epoch advance allows the deliberately
   rebranded v3.x→v1.1 transition; the internal build must still increase. Within
   an epoch a display downgrade is rejected. An old epoch is always rejected,
   even with a higher display label or feed sequence. A same-display rebuild
   still needs a new build and sequence. Schema1 manifests are not accepted.
   The staged app must match the signed `CFBundleVersion` and integer
   `ATLASUpdateEpoch`. The delivered v3.6 bundle has build1 and no epoch key;
   treat that reviewed legacy lineage as epoch0 only during the explicit native
   migration, never infer order from its upstream short version1.5.4. The
   reviewed First Light RC2 has native build3 and explicit epoch1. This is
   metadata evidence, not updater activation: trusted receipt integration and
   the actual installer still remain to implement and verify.
4. An approved GitHub asset URL can redirect only through the observed official
   release asset transport. A future downloader must allowlist exact HTTPS
   redirect hosts from verified vendor documentation, cap redirects and bytes,
   reject URL credentials/downgrades, avoid all auth/cookie forwarding to a new
   host and honor cancellation/timeouts. There is NO downloader in this module.
5. Verify a bounded immutable archive snapshot, then reject traversal, absolute
   and ambiguous paths, case/normalization collisions, duplicate entries,
   symlinks/special files, encryption, unsupported compression, oversized members
   and unexpected roots/private state. A public update contains only ATLAS.app
   and explicitly allowed public release documents. Optional Profile is excluded.
6. Stage only in a NEW private owner-controlled directory. Independently verify
   bundle identity, executable/platform/minimum OS, all nested code signatures
   and publisher trust before presenting it as installable. `codesign --verify`
   on an ad-hoc app proves integrity, NOT independent publisher identity. The
   prototype requires a trusted native callback and rejects a missing callback.
   It never installs, launches or mutates an existing app or user profile.
7. Recheck idle state and the approved immutable target/release at the final
   installation boundary. The owner must be able to cancel before replacement.
   Stop cannot undo replacement or an already dispatched app action. Installer
   behavior against hostile same-user filesystem replacement needs a dedicated
   review; private staging alone is not a complete same-user sandbox.

## Installation transaction still to implement and verify

Use Sparkle's reviewed installer/rollback machinery where practical. Do not
compose installation from `rm -rf` and `unzip`, run upstream `build.sh`, require
routine administrator rights or touch LaunchAgents/Keychain/permissions.

The installation must bind the exact existing customized app, reject symlink or
changed destinations, preserve its old bundle in a recoverable backup, and use
a same-volume atomic replacement. A single trusted lock/transaction ID prevents
duplicate installs. Durable state should distinguish prepared, old backed up,
new active and verified committed. A crash/uncertain filesystem outcome causes
inspection/reconciliation, never blind retry. If the new app cannot be verified
or launched, offer rollback to the verified old bundle. Rollback changes the app
only, not profile/runtime/Keychain/vault contents or completed external actions.

Do not update while a job, approval, capture or unsaved app interaction is active.
Real update/cancel/crash/rollback tests need two separate disposable signed app
fixtures and a temporary installation directory before any owner installation.

## Exact owner gate before production activation

Signing approval is not the only remaining work. The downloader, maintained
installer integration, native update UI, trusted receipts, crash reconciliation
and real update/rollback tests above are still incomplete. Do not describe this
component as ready merely because a key has been approved or created.

The owner must approve creation/use of ONE persistent release-signing identity
and its secure custody/backup. Provision it locally using the supported signing
tool, show the public fingerprint independently, embed only the public key, and
keep the private key out of Git, release assets, the app, logs and public hosting.
For Sparkle the documented key generator writes the private key to the login
Keychain; it has NOT been run. No key or Keychain access prompt may be approved
by an agent. Signing release content is an executable-code trust boundary.

Developer ID/notarization is a separate Apple distribution decision. The current
ad-hoc build is not notarized. Do not claim it is or bypass Gatekeeper/SIP or strip
quarantine. See [Apple's notarization documentation](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution).

After provisioning, independent review must verify the selected Sparkle version,
signatures/feed/notes, release-channel behavior, downgrade and expiry handling,
actual UI approval/cancel, corrupted archives, duplicate clicks, idle waiting,
signature failures, interruption, restart reconciliation and rollback. Until
then the app should say: **Manual updates; signed in-app installation is not
configured.** A check-only link must not be labeled an installed update.

## Every-release workflow

1. Freeze a clean reviewed source revision and record exact tests/known limits.
2. Update About, current-version metadata, README, CHANGELOG and release notes.
   Distinguish unit/mock/native/live/skipped evidence and actual upload time.
3. Build without installation or side effects; prepare a public app-only update
   asset and separate public download instructions. Keep private companions in
   their private Library identity only, never in public source/release history.
4. Run exact-build signatures/resource/privacy/license/relocation checks. Test
   supported OS/architecture/runtime requirements; label unavailable hardware.
5. Commit the sanitized public export with a meaningful message and provenance;
   preserve legal attribution and no Co-authored-by trailers. Push a new tag,
   never rewrite a released tag or overwrite its asset bytes.
6. Publish an explicitly labeled prerelease or stable release with its detailed
   changelog, source revision, actual test evidence, setup/rollback notes and
   asset digest. Verify the returned remote tag, release status and exact digest.
7. Once signing is approved/configured, sign the actual immutable update asset
   and feed/notes using supported tooling. Publish the signed feed only after
   its referenced asset exists and validates. Never upload a signing secret.
8. Perform an update from the previous disposable build, then promote only the
   verified channel. Keep previous releases available for manual rollback.

For the current unsigned development fixtures run:

```
python3 -m unittest discover -s scripts/personal-release -p 'test_update_verify.py'
swiftc -typecheck scripts/personal-release/UpdateTrust.swift
```

Those tests use a deliberately fake verification callback to exercise metadata
and archive policy. They are NOT evidence that real signatures, a native update
UI, network download, installation, crash recovery or rollback have been tested.
