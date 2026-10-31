#!/bin/sh
set -eu
# Native filesystem tests only. Every bundle and journal is an isolated fixture.
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
work=$(mktemp -d "${TMPDIR:-/tmp}/atlas-transaction-compile.XXXXXXXX")
trap 'rm -rf -- "$work"' EXIT HUP INT TERM
swiftc -warnings-as-errors "$repo/updater/UpdateTransaction.swift" "$repo/updater/tests/UpdateTransactionTests.swift" -o "$work/tests"
"$work/tests"
