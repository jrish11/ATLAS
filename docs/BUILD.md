# Build and test

These instructions apply to the current Mac v3.5 source, not every historical archive. Requirements observed for the delivered artifact: Apple Silicon, macOS26+, Apple command-line tools/Swift SDK, working `/usr/bin/python3`. No cross-device or Intel artifact is certified by these results.

## Isolated build

Do NOT run upstream `build.sh` or `install.sh` on the owner's machine as a build-only check. They can install/replace an app, import a signing identity or change startup state. Use the separate build-only script:

```sh
ATTICUS_DEV_OUTPUT="$PWD/build/ATLAS-review.app" bash build-personal-dev.sh
```

Choose a new nonexistent output path; explicit existing outputs are rejected. This compiles, packages and ad-hoc signs; it does not install, launch, change Keychain, create startup persistence or grant permissions. The build defaults to no bundled Pi/Node runtime. Do not set `ATTICUS_PI_RUNTIME`/`ATTICUS_NODE_BINARY` casually: that optional path copies third-party code and re-signs Node. The verified release strategy is app-only with explicit per-device setup and license checks.

Run software self-tests with an isolated temporary profile only:

```sh
profile_dir=$(mktemp -d)
ATTICUS_DIR="$profile_dir" build/ATLAS-review.app/Contents/MacOS/Atticus --selftest
ATTICUS_DIR="$profile_dir" build/ATLAS-review.app/Contents/MacOS/Atticus --settings-only-selftest
```

These test modes do not prove microphone/recognition/UI success. Never activate real voice, browser access, remote listeners or provider tasks as part of an offline suite. Host-guarded UI tests are not to be bypassed on an owner's Mac.

## Offline checks

`bash scripts/run-offline-checks.sh` runs the bounded synthetic regression selection and packaging tests. Node is used for actual JavaScript fixtures where available. No real credentials, network/provider requests, app control or real files are required. Run from this export root; tests isolate local state.

## Runtime setup and packaging

The app requires supported Node22.19+/npm and its explicitly confirmed per-device Pi bootstrap for foreground OpenAI. Keys are entered locally into namespaced Keychain. Codex0.155.1 account mode is separate. Do not copy credentials or authenticated browser sessions. See the bundled `Setup/FIRST-RUN.md` after release staging or `scripts/personal-release/FIRST-RUN.md` in source.

`scripts/personal-release/stage_external.py` validates exact candidate hash/source resources and stages a sanitized app-only ZIP. It requires a full source commit available in Git. This documentation/sanitization export is deliberately not yet a Git repository and its sanitized files differ from original history; do not claim the original commit validates modified export files. Final publication must create a reviewed export commit and rebuild/revalidate against that commit, or package the unchanged verified source tree separately. Original commits are listed for traceability, not as a substitute for export validation.

Windows source is in a separate experimental archive. Its native build, runtime, installer, sandbox and signing remain unverified; no Windows build is produced on this Mac. Review its own development guide before a Windows test machine is used.
