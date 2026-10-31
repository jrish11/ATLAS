#!/bin/bash
set -eu
cd "$(dirname "$0")/../.."
TEMP=$(mktemp -d "${TMPDIR:-/tmp}/atlas-archive-tests.XXXXXX")
trap 'rm -rf "$TEMP"' EXIT
# realpath canonicalizes Darwin /var to /private/var for strict no-link tests.
TEMP=$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$TEMP")
mkdir -p "$TEMP/input/ATLAS.app/Contents/MacOS" "$TEMP/input/ATLAS.app/Contents/Resources/Licenses" "$TEMP/install"
chmod 700 "$TEMP/install"
printf 'print("fixture only")\n' > "$TEMP/main.swift"
swiftc -target "$(uname -m)-apple-macos26.0" "$TEMP/main.swift" -o "$TEMP/input/ATLAS.app/Contents/MacOS/Atticus"
for name in PersonalKeychain ATLASUpdateInstaller; do cp "$TEMP/input/ATLAS.app/Contents/MacOS/Atticus" "$TEMP/input/ATLAS.app/Contents/MacOS/$name"; done
python3 - "$TEMP" <<'PY'
import plistlib,sys,pathlib
r=pathlib.Path(sys.argv[1]);p=r/'input/ATLAS.app/Contents'
(p/'Info.plist').write_bytes(plistlib.dumps(dict(CFBundleIdentifier='com.atticus.personal.dev',CFBundleExecutable='Atticus',CFBundlePackageType='APPL',CFBundleVersion='4',CFBundleShortVersionString='1.2.0',ATLASUpdateEpoch=1,LSMinimumSystemVersion='26.0')))
for name in ('Atticus-MIT.txt','Plip-MIT.txt'): (p/'Resources/Licenses'/name).write_text('Synthetic test notice only\n')
PY
codesign -s - --force "$TEMP/input/ATLAS.app" >/dev/null 2>&1
python3 - "$TEMP" <<'PY'
import zipfile,pathlib,sys
r=pathlib.Path(sys.argv[1])
with zipfile.ZipFile(r/'release.zip','w',zipfile.ZIP_DEFLATED) as z:
 for p in sorted((r/'input').rglob('*')):
  if p.is_file(): z.write(p,p.relative_to(r/'input'))
PY
swiftc -D UPDATER_TESTING updater/UpdateManifest.swift updater/UpdateTransaction.swift updater/UpdateStaging.swift updater/tests/ArchiveTests.swift -o "$TEMP/tests"
"$TEMP/tests" "$TEMP/release.zip" "$TEMP/install" "$PWD/updater/extract_update.py"
