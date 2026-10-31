# ATLAS 1.1 — First Light

**DRAFT / RELEASE CANDIDATE — NOT A PRODUCTION-READY DOWNLOAD.**

This is the proposed naming for the next public release line. It does not change
the fact that v3–v3.6 were already public experimental previews with published
source tags and release records. Those records and downloads are retained.
The current published Mac preview remains v3.6 until a separately reviewed
candidate passes its release gates. No v1.1 tag, final artifact, stable update
feed or ready phone connection is asserted by this draft.

## Intended fixes and retained behavior

- Repair Start task in embedded file-origin WebKit when crypto.randomUUID is
  unavailable, using cryptographic getRandomValues only; fail closed if secure
  randomness is unavailable. Tests must cover duplicate Start/Continue, late
  callbacks, cancellation, pending recovery and restart without repeat actions.
- Offer a real explicit Codex / Claude Code provider choice using their respective
  existing accounts. The foreground OpenAI Terra6.1 API key remains separate.
  Native task confirmation and sandbox/approval boundaries remain mandatory.
- Retain the compact original interface, verified deterministic command routes,
  owner-confirmed memory, local folder controls, background safeguards and
  System/Light/Dark Settings from the previews. Do not imply every inherited
  feature has been live-verified.
- Show First Light branding without changing the existing customized app/profile,
  runtime, Keychain or bundle identity. Do not overwrite official Atticus or the
  unrelated earlier ATLAS prototype. Preserve upstream MIT/Plip notices.

## Release gates still required

| Gate | Current evidence / remaining work |
| --- | --- |
| Reported request-ID bug | 158 focused checks passed on frozen5b2040f; one native WebKit test skipped by host restriction. Actual safe embedded-engine verification or supervised owner test is still required. |
| Final candidate | Exact combined source/binary, version/build, resources, regression suite, signatures, relocation, license/privacy scan and changelog must be frozen and rechecked. No final v1.1 hash is assigned here. |
| Codex end-to-end | Integrated native Start/progress/approval/cancel/restart outcome needs an actual supervised scoped account task. Old backend/fixture success is not this acceptance test. |
| Claude Code choice | New entry requires Safe mode and sandbox; account-only environment/tool tests are synthetic. Actual supported account execution/approval outcomes remain unverified. |
| MacBook core | Voice/wake, OS permission denial/retry, authenticated browser reuse and actual native UI/background behavior need checks on the target Mac. |
| Phone pairing | Persistent native gateway, approved private route, actual device pairing, replay/revocation/restart and real bounded task must pass before install/pair instructions say ready. Current separate prototypes are not a ready feature. |
| Windows | Source-only status remains. The reviewed manual cloud workflow has not run: existing GitHub credential lacks workflow permission. No Windows binary is invented or advertised. |
| In-app update | No signing identity, trusted signed feed or installer has been activated. Manual replacement remains the current behavior. |

## Version order and migration

The product display label changes from preview3.x to1.1; that is deliberate
branding, not permission to roll back code. All delivered v3.6 bundles have
internal CFBundleVersion1; the proposed candidate advances it to2 while retaining
the upstream component version1.5.4 separately. The signed-updater development
prototype uses a publisher-signed update epoch plus globally increasing build
and feed sequence, so a reviewed epoch transition may use the lower display
label. Old epochs/builds cannot replay as updates. This remains a prototype, not
an installed migration or enabled feed. A trusted native receipt and explicit
ATLASUpdateEpoch must be integrated before activation.

Do not delete or reset a profile, Keychain, runtime, vault or browser session for
this naming transition. Back up the old customized app bundle before replacement
and preserve it for rollback. App rollback does not undo completed external work
or confirmed memory edits. No automatic security permission is granted.

## Final release-note fields to fill only from evidence

- Frozen original source and sanitized public snapshot/tag.
- Final artifact URL, exact size/SHA256, signing/notarization status and platform.
- Unit/mock/native/live pass/fail/skipped counts and measured scenario timings.
- Current provider/account/runtime requirements; verified and unsupported actions.
- Remaining manual permissions/setup, rollback and known defects.

No production-ready label, latest stable download switch or phone-pair notification
until the relevant gates above are resolved. No new model/API calls were made to
prepare this draft. Historical public previews are not reclassified as never
published.
