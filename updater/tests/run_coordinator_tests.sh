#!/bin/bash
set -eu
cd "$(dirname "$0")/../.."
TEMP=$(mktemp -d "${TMPDIR:-/tmp}/atlas-update-tests.XXXXXX")
trap 'rm -rf "$TEMP"' EXIT
swiftc updater/UpdateManifest.swift updater/UpdateDownload.swift updater/UpdateTransaction.swift updater/UpdateStaging.swift updater/UpdateCoordinator.swift updater/tests/CoordinatorTests.swift -o "$TEMP/tests"
"$TEMP/tests"
