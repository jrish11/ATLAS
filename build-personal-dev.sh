#!/bin/bash
# Build only. No installation, Keychain import, login item, permissions or app launch.
set -eu
cd "$(dirname "$0")"
ROOT="$(pwd)"
OUT="${ATTICUS_DEV_OUTPUT:-$ROOT/build/Atticus Dev.app}"
CACHE="${ATTICUS_DEV_CACHE:-$ROOT/build/compiler-cache}"
if [ -n "${ATTICUS_DEV_OUTPUT:-}" ]; then
  case "$OUT" in /*) ;; *) echo "Candidate output must be absolute." >&2; exit 1 ;; esac
  if [ -e "$OUT" ] || [ -L "$OUT" ]; then echo "Candidate output already exists; refusing to replace it." >&2; exit 1; fi
fi
STAGE="$(mktemp -d "${TMPDIR:-/tmp}/atticus-dev.XXXXXX")"
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$CACHE/clang" "$CACHE/swift" "$STAGE/Atticus Dev.app/Contents/MacOS" "$STAGE/Atticus Dev.app/Contents/Resources/ui"
export CLANG_MODULE_CACHE_PATH="$CACHE/clang"
swiftc -module-cache-path "$CACHE/swift" -O -target "$(uname -m)-apple-macos26.0" Atticus.swift -o "$STAGE/Atticus Dev.app/Contents/MacOS/Atticus"
swiftc -module-cache-path "$CACHE/swift" PersonalKeychain.swift -o "$STAGE/Atticus Dev.app/Contents/MacOS/PersonalKeychain"
cp atticus.py personal_commands.py memory_destinations.py memory_inspector.py memory_transactions.py memory_seed.py folder_grants.py autonomy_policy.py approval_channel.py memory_rules_store.py memory_corrections.py memory_workflows.py foreground_openai.py foreground_control.py foreground_smoke.py codex_provider.py vault_journal.py keychain_store.py "$STAGE/Atticus Dev.app/Contents/Resources/"
cp ui/*.html ui/*.js ui/AppIcon.icns "$STAGE/Atticus Dev.app/Contents/Resources/ui/"
cp ui/AppIcon.icns "$STAGE/Atticus Dev.app/Contents/Resources/"
# Copy only the explicitly supplied public Pi distribution and Node runtime.
if [ -n "${ATTICUS_PI_RUNTIME:-}" ] && [ -n "${ATTICUS_NODE_BINARY:-}" ]; then
  mkdir -p "$STAGE/Atticus Dev.app/Contents/Resources/pi-runtime/bin"
  cp -R "$ATTICUS_PI_RUNTIME/node_modules" "$STAGE/Atticus Dev.app/Contents/Resources/pi-runtime/"
  cp -L "$ATTICUS_NODE_BINARY" "$STAGE/Atticus Dev.app/Contents/Resources/pi-runtime/bin/node"
  codesign -s - --force "$STAGE/Atticus Dev.app/Contents/Resources/pi-runtime/bin/node"
fi
VERSION=$(tr -d '\n' < VERSION)
cat > "$STAGE/Atticus Dev.app/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleIdentifier</key><string>com.atticus.personal.dev</string>
<key>CFBundleName</key><string>ATLAS</string>
<key>CFBundleDisplayName</key><string>ATLAS</string>
<key>CFBundleExecutable</key><string>Atticus</string>
<key>CFBundleVersion</key><string>2</string>
<key>CFBundleShortVersionString</key><string>$VERSION</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleIconFile</key><string>AppIcon</string>
<key>LSUIElement</key><true/>
<key>NSMicrophoneUsageDescription</key><string>ATLAS listens when you use its shortcut or microphone button.</string>
<key>NSSpeechRecognitionUsageDescription</key><string>ATLAS turns your words into text on this Mac.</string>
<key>NSAppleEventsUsageDescription</key><string>ATLAS controls apps when you ask it to.</string>
<key>NSCalendarsFullAccessUsageDescription</key><string>ATLAS accesses your calendar when requested.</string>
</dict></plist>
PLIST
codesign -s - --force "$STAGE/Atticus Dev.app"
mkdir -p "$(dirname "$OUT")"
if [ -z "${ATTICUS_DEV_OUTPUT:-}" ]; then rm -rf "$OUT"; fi
mv "$STAGE/Atticus Dev.app" "$OUT"
printf 'Built %s\n' "$OUT"
