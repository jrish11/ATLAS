#!/bin/sh
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
work=$(mktemp -d "${TMPDIR:-/tmp}/atlas-manifest-test.XXXXXXXX")
trap 'rm -rf -- "$work"' EXIT HUP INT TERM
swiftc -warnings-as-errors -D UPDATER_TESTING "$repo/updater/UpdateManifest.swift" "$repo/updater/UpdateDownload.swift" "$repo/updater/tests/ManifestTests.swift" -o "$work/fixtures"
"$work/fixtures"
swiftc -warnings-as-errors "$repo/updater/UpdateManifest.swift" "$repo/updater/UpdateDownload.swift" "$repo/updater/tests/ManifestTests.swift" -o "$work/production"
"$work/production"
