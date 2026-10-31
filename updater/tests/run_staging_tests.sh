#!/bin/bash
set -eu
cd "$(dirname "$0")/../.."
TEMP=$(mktemp -d "${TMPDIR:-/tmp}/atlas-staging-tests.XXXXXX")
trap 'rm -rf "$TEMP"' EXIT
swiftc updater/UpdateManifest.swift updater/UpdateTransaction.swift updater/UpdateStaging.swift updater/tests/StagingTests.swift -o "$TEMP/tests"
"$TEMP/tests"
