#!/bin/sh
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
work=$(mktemp -d "${TMPDIR:-/tmp}/atlas-installer-compile.XXXXXXXX")
trap 'rm -rf -- "$work"' EXIT HUP INT TERM
sources="$repo/updater"
swiftc -warnings-as-errors -D UPDATER_TESTING "$sources/UpdateManifest.swift" "$sources/UpdateTransaction.swift" "$sources/UpdateDownload.swift" "$sources/UpdateStaging.swift" "$sources/UpdateCoordinator.swift" "$sources/UpdateInstaller.swift" "$repo/updater/tests/InstallerTests.swift" -o "$work/tests"
"$work/tests"
swiftc -warnings-as-errors -D ATLAS_UPDATE_INSTALLER "$sources/UpdateManifest.swift" "$sources/UpdateTransaction.swift" "$sources/UpdateDownload.swift" "$sources/UpdateStaging.swift" "$sources/UpdateCoordinator.swift" "$sources/UpdateInstaller.swift" -o "$work/helper"
# A direct CLI invocation must not become an installation channel.
if "$work/helper" </dev/null >/dev/null 2>/dev/null; then
  echo 'FAIL: helper accepted non-pipe invocation' >&2
  exit 1
fi
