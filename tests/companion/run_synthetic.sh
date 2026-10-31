#!/bin/bash
# Synthetic data only. --loopback additionally binds 127.0.0.1 and exercises
# a disposable fsynced temporary store; it may need local sandbox permission.
set -eu
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/atlas-companion-check.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/clang" "$WORK/swift"
export CLANG_MODULE_CACHE_PATH="$WORK/clang"
cd "$ROOT"
compile() { swiftc -target "$(uname -m)-apple-macos26.0" -module-cache-path "$WORK/swift" companion/Shared/*.swift "$@"; }
for test in enrollment completion devices proof routes response vault coordinator http http_e2e; do
  compile "tests/companion/${test}_fixture.swift" -o "$WORK/$test"
  "$WORK/$test"
done
for test in webcrypto_host proof_webcrypto_host response_webcrypto_host webcrypto_completion_host; do
  compile "tests/companion/${test}.swift" -o "$WORK/$test"
done
node tests/companion/webcrypto_fixture.js "$WORK/webcrypto_host"
node tests/companion/proof_webcrypto.js "$WORK/proof_webcrypto_host"
node tests/companion/response_webcrypto.js "$WORK/response_webcrypto_host"
node tests/companion/webcrypto_completion.js "$WORK/webcrypto_completion_host"
if [ "${1:-}" = "--loopback" ]; then
  compile tests/companion/qr_fixture.swift -o "$WORK/qr"
  "$WORK/qr"
  compile tests/companion/SyntheticFileStorage.swift tests/companion/full_http_webcrypto_host.swift -o "$WORK/http-host"
  node tests/companion/full_http_webcrypto.js "$WORK/http-host" --http-recovery
  node tests/companion/full_http_webcrypto.js "$WORK/http-host" --durable
  node tests/companion/full_http_webcrypto.js "$WORK/http-host" --ack-loss
fi
