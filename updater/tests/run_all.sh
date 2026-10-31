#!/bin/bash
set -eu
cd "$(dirname "$0")/../.."
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PWD/updater"
python3 -m unittest discover -s updater/tests -p 'test_*.py' -q
for component in manifest download transaction coordinator staging archive installer; do
  bash "updater/tests/run_${component}_tests.sh"
done
swiftc -warnings-as-errors -typecheck updater/UpdateManifest.swift updater/UpdateDownload.swift updater/UpdateTransaction.swift updater/UpdateStaging.swift updater/UpdateCoordinator.swift updater/SignedUpdateWindow.swift updater/UpdateInstaller.swift
printf 'Aggregate updater checks passed. Native interactive UI, activated signed feed and owner installation remain unverified.\n'
