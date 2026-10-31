# Private Atticus release staging

This tool produces a **local development ZIP**, never installs, launches, uploads, grants permissions, or copies a user profile. It requires an already built app with the bundle-relative Pi resolver and bundled Node/Pi runtime. It refuses old `task-6`-relative candidates, nonmatching approved hashes, runtime symlinks outside the bundle, state-like filenames, missing package license texts, and an existing output. It retains the upstream Atticus and Plip MIT notices, the supplied Node distribution license, each package's own included license, and separately supplied missing notices. The archive records file hashes, package versions, and the source commit. ZIP entry ordering and timestamps are fixed; byte reproducibility is demonstrated only for the unsigned fixture, not claimed for ad-hoc-signed releases.

## Inputs that must be independently verified

- A final, reviewed, isolated `com.atticus.personal.dev` bundle built from a committed source revision, with its executable SHA-256. The stager matches each Python and UI resource against that Git commit; it does not prove that a reviewed commit contains no sensitive content.
- A bundle-relative Pi 1.4.0 runtime and Node 22.19.0 or newer, built for Apple Silicon. Independently verify the Node binary against the official Node distribution's checksums and its license against that same distribution. Independently verify each npm tarball against its lockfile integrity before approving the extracted runtime. An inventory created from an existing `node_modules` is not proof of provenance.
- A reviewed runtime inventory. Generate it without network access using:

  ```sh
  python3 scripts/personal-release/runtime_inventory.py --runtime /path/to/App.app/Contents/Resources/pi-runtime --output /private/staging/runtime-inventory.json
  ```

  Review and compare it to trusted vendor artifacts. The stager checks it before and after copying. No keys, profiles, logs, vaults, or browser data belong in that runtime.
- The Node distribution's complete `LICENSE` and an audited directory of missing npm license texts. For each package lacking a root `LICENSE`, `LICENCE`, or `COPYING` file, supply the exact version's license as `SHA256("name@version").txt`. The script prints the missing package names and refuses to proceed; do not invent or truncate notices. In particular, the inspected local Pi runtime was missing license texts for 13 named packages. The package metadata lists Pi as MIT, but metadata alone is not a substitute for the license text.

Upstream references: [Pi documentation](https://github.com/earendil-works/pi) and [Node distribution](https://nodejs.org/en/download). The Pi documentation describes a local npm install with lifecycle scripts disabled; this staging tool performs no install or download.

## Stage after final integration

```sh
python3 scripts/personal-release/stage.py \
  --app /private/staging/Atticus.app \
  --output /private/staging/Atticus-Dev.zip \
  --expected-executable-sha256 APPROVED_SHA256 \
  --expected-node-sha256 APPROVED_NODE_SHA256 \
  --source-commit FULL_REVIEWED_COMMIT \
  --node-license /private/staging/Node-LICENSE \
  --vendor-notices /private/staging/notices \
  --runtime-manifest /private/staging/runtime-inventory.json
```

The script uses an ad-hoc signature and verifies it locally. It does **not** create a Developer ID signature, notarize, or guarantee Gatekeeper acceptance. Do not distribute the resulting app until the source and dependency provenance, all license notices, native add-on architecture/signatures, package contents, and end-to-end behavior have been reviewed. The currently inspected integrated candidate lacks the required bundled Pi/Node layout; it is not a valid input. Codex remains a separate installation and account login, with live dispatch gated. Foreground OpenAI uses the key entered separately on each Mac; keys and authenticated browser sessions are never transferred. The app also invokes `/usr/bin/python3`; availability on the target must be verified without automatically installing developer tools.

Apple Silicon and macOS 26+ are the minimum indicated by the inspected binary. The MacBook's actual architecture, OS version, permissions, dependencies, and launch remain untested. Each Mac must grant its own permissions when needed. No synchronization is configured.

## Offline fixture checks

```sh
PYTHONPYCACHEPREFIX=/tmp/atticus-release-cache python3 scripts/personal-release/test_stage.py -v
```

These use fake executables, a fake key and an isolated temporary profile. They relocate and inspect a ZIP without launching the real app or calling a provider. They do not validate notarization, the genuine Pi/Node supply chain, or a MacBook installation.

## Dependency provenance investigation

`provenance.py` downloads the 13 identified public npm archives without executing package code. It verifies each registry SHA-512 against the lockfile, checks npm metadata and tarball identity, compares installed files, and records the exact source URL, version and hashes for each notice it can substantiate. `verify_cached_archives.py` independently checks the saved archives and detects extra installed files offline. In the inspected runtime, all 13 archives and **2,948 installed files** matched their lockfile integrity and archive contents. Nine license notices were located at their exact source revisions. Four remain unresolved:

- `@aws-sdk/credential-provider-http@3.972.82`
- `@aws-sdk/credential-provider-login@3.972.87`
- `@aws-sdk/nested-clients@3.997.54`
- `proxy-agent-negotiate@1.1.0`

The three AWS tarballs omit root license texts and their registry metadata did not identify a source commit or matching exact-version repository tag. The proxy package declares MIT, but its pinned archive and inspected exact source tree did not contain the required license text. These are packaging blockers; do not invent notices or substitute current source text. Seven Pi notices were traced through npm provenance statements to the source commit; the statements' signatures were not independently verified by this tool. An isolated `npm audit signatures --json` exited successfully with empty `invalid` and `missing` lists, but its output did not provide a verification count.

Node v22.23.1's local arm64 binary matched the binary inside the official release archive and the archive's HTTPS-published SHA-256. The official distribution's complete Node license is in local staging. Its existing code signature passed `codesign --verify --strict` outside the outer execution sandbox. Detached release-checksum signature verification was not performed because a suitable OpenPGP verifier and trusted release-key setup were unavailable; this is not a claim of independently signature-verified download provenance. The arm64 Pi native add-on matched its SHA-512-verified npm archive and reports macOS 11.0 as its binary minimum; this does not replace target-Mac execution testing. Preserve the official Node binary signature rather than ad-hoc re-signing the binary: ad-hoc signing changes its file hash. The inspected portable candidate had already re-signed Node, so its bundled Node no longer matched the official binary hash.

## Proposed per-device first-run fallback

If the four redistribution notices cannot be established, a separate user-initiated first-run setup can obtain the pinned packages directly from the public npm registry on each Mac instead of redistributing this local `node_modules` tree. `bootstrap_runtime.py` requires a verified Node executable and npm CLI already installed by the owner, a new absolute output directory, and explicit `--confirm-download`. It uses the included public lockfile, isolated temporary npm configuration and cache, verifies registry-only SHA-512-pinned entries, and runs `npm ci --ignore-scripts` without a global install. Failure leaves an `INCOMPLETE` marker for inspection. This script has only mocked tests and **has not been run against the real registry or on the MacBook**.

The present app resolver searches its bundle, not this proposed external runtime. The source owner must explicitly add and test a per-device runtime lookup before this fallback can work; do not claim that running the script alone configures Atticus. A future integrated command would look like:

```sh
python3 scripts/personal-release/bootstrap_runtime.py \
  --output "$HOME/Library/Application Support/Atticus Dev/pi-runtime" \
  --node /path/to/verified/node --npm-cli /path/to/verified/npm-cli.js \
  --confirm-download
```

No first-run installation, key migration, global settings, permissions, or startup changes were performed here.

## Supported core-only limited-test package

The source adapter now supports `~/Library/Application Support/Atticus Dev/pi-runtime` when no bundled runtime exists. An external `runtime.json` records the local verified Node path and hash; Node is not copied, re-signed or transferred. `INCOMPLETE`, symlinked roots, invalid descriptors and changed Node binaries are refused. `bootstrap_runtime.py` writes this descriptor only after the pinned installation succeeds.

Use `stage_external.py` to create an app containing only Atticus's approved source resources, its upstream notices, and the explicit first-run setup/lockfile. It excludes **all Node/Pi runtime files**, including an older runtime already inside the input app. This avoids redistributing the four unresolved packages. Its first-run setup obtains the packages directly from the official registry with the owner's confirmation; it does not certify a missing upstream notice or transfer another Mac's credentials.

```sh
python3 scripts/personal-release/stage_external.py \
  --app /private/staging/Atticus-final-candidate.app \
  --output /private/staging/Atticus-Core-Limited-Test.zip \
  --expected-executable-sha256 APPROVED_FINAL_SHA256 \
  --source-commit FULL_FINAL_COMMIT
```

The commit must contain both the candidate's exact source resources and these setup files. The app is suitable for **limited testing with prerequisites**, not a claim of complete readiness: Apple Silicon, macOS 26+, working Python, and owner-installed verified Node/npm are required before foreground use; Codex is installed and authenticated separately. Ad-hoc signing remains a distribution limitation. No final candidate should be called tested merely because its staging step passed.

Validation performed: a real isolated `npm ci --ignore-scripts` installed 121 packages; the external resolver found Pi 1.4.0 from a fake user home and `pi --version` returned 1.4.0 without a model call. A real empty-cache offline install failed and retained `INCOMPLETE`. Mocked tests cover cancellation before download and existing-directory refusal. A relocated core-only ZIP fixture refuses missing and incomplete runtimes, then resolves the explicitly configured fake per-device runtime. This does not validate the owner's MacBook or grant its permissions.
