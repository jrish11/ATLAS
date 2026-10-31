#!/bin/sh
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
work=$(mktemp -d "${TMPDIR:-/tmp}/atlas-download-test.XXXXXXXX")
trap 'rm -rf -- "$work"' EXIT HUP INT TERM
swiftc -warnings-as-errors -D UPDATER_TESTING "$repo/updater/UpdateManifest.swift" "$repo/updater/UpdateDownload.swift" "$repo/updater/tests/DownloadTests.swift" -o "$work/fixtures"
"$work/fixtures"
