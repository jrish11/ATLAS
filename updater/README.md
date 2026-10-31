# Signed-only updater development

This branch adds a separate native update window to the owner's existing **Check updates** action. The floating assistant interface, app identity and existing profile/Keychain namespaces remain unchanged.

**Release gate: disabled.** `UpdatePublisherTrust.keys` is an empty compiled map. Checks stop before filesystem or network activity when it is empty. There is no remote, environment or settings override. No production publisher key was generated or accessed. A future approved key ceremony, public-key fingerprint verification, immutable release assets and signed feed publication are required before activating this system. Developer ID/notarization is a separate prerequisite for a notarized distribution; an ad-hoc signature is not notarization.

The protocol authenticates the exact manifest bytes using Ed25519 before parsing authority. It binds repository, bundle identifier, architecture, minimum OS, archive hash/size, release epoch/build/sequence, channel and expiry. Epoch permits the historical 3.x preview → 1.1 naming transition while the build and sequence must increase. Release notes are plain text. No unsigned or checksum-only fallback is accepted.

Downloads use ephemeral URLSession storage with no shared cookies, cache or credential store. The initial GitHub repository route and each release-asset redirect are allowlisted, requests are rebuilt without Authorization, and response size and cancellation are bounded. Extraction rejects traversal, links, special files, collisions, oversized members and private-state roots. Python extraction is unprivileged and is **not** signature or installation authority. Native code verifies archive bytes, the complete app code signature, bundle identity, release order and Mach-O platform metadata.

The first transition into the updater-protocol build must be a manual app replacement. Only releases with the startup interlock and `ATLASUpdateInstallerProtocol=1` can participate in later in-app replacement. The native app holds a shared per-target startup lock before profile/bootstrap; the helper waits for its verified parent's kernel exit event and takes an exclusive lock before exchange. Another cooperating instance blocks installation. A startup acknowledgement is a process identity/liveness receipt, not a claim that every app feature works.

The filesystem transaction requires owner-controlled, same-volume direct app siblings and a separate private state directory. It binds old/new complete tree digests, writes and syncs its journal before atomic exchange, retains the old bundle, and never replays an uncertain transaction after a crash. Recovery reports the observed state for explicit review. Settings, Keychain, runtime descriptors, personal files and vault data are never included or restored.

## Tests

Run scripts under `updater/tests/` individually or use the aggregate runner when supplied. They use temporary fake bundles, short synthetic subprocesses, ephemeral signing keys and mocked transports. No installed app, provider, microphone, owner profile or real signing key is used. Native window interaction, real signed-feed publication, owner-app quit/relaunch and physical MacBook compatibility require separate release validation; test counts do not establish those outcomes.

Same-user hostile process mutation is not an OS security boundary. Filesystem identity checks reduce accidental/stale replacement and fail closed when changes are detected. No routine admin privileges, security-warning bypass, Gatekeeper/SIP changes or permission grants are part of this updater.

## Local backup trust and recovery

A local backup restore is a separate, explicitly owner-confirmed action bound to the prior installed bundle's complete private journal digest and code signature. The initial manual installation is that old version's trust anchor. This is **not** a publisher-signed rollback authorization and does not authorize downloading an older release. Network installation continues to require the exact signed manifest and archive. A failed new child can trigger rollback only after its exit is confirmed and an exclusive startup lock is reacquired; a live or uncertain process is never swapped underneath.

Inspection is read-only. An unchanged, provably unstarted transaction can be discarded by a separate native confirmation; its candidate stays available for inspection. An uncertain transaction is not silently reset or retried. The native window's close/cancel action discards its own completed download through descriptor-relative cleanup and does not delete a retained backup or edit user data.

See `TEST-RESULTS-2026-10-31.md` for exact fixture counts, the separate real public-download probe, build evidence and remaining gates. The optional real probe is not run by the offline aggregate.
