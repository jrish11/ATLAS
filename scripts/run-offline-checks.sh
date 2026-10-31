#!/bin/bash
# Synthetic/local checks only. No app launch, provider task, installation or permission grants.
set -eu
cd "$(dirname "$0")/.."
profile_dir=$(mktemp -d "${TMPDIR:-/tmp}/atlas-offline.XXXXXX")
trap 'rm -rf "$profile_dir"' EXIT
export ATTICUS_DIR="$profile_dir"
export PYTHONDONTWRITEBYTECODE=1
export ATTICUS_POSTHOG_KEY=''
python3 -m unittest tests.test_codex_workspace tests.test_codex_start_controls tests.test_native_scope_gate tests.test_codex_provider tests.test_codex_native_authority tests.test_codex_cancellation tests.test_direct_media tests.test_approval_integration tests.test_approval_channel tests.test_foreground_control -q
python3 -m unittest discover -s scripts/personal-release -p 'test_*.py' -q
