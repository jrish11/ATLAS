"""Assemble an external-Python Windows test package; no installs or execution."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import stat
import struct

STATE = {'.env', 'settings.json', 'atticus.json', 'memory.md', 'recent.jsonl',
         'log.jsonl', 'auth.json', 'license.key'}
MODULES = ('atticus.py', 'winctl.py', 'codex_account.py', 'codex_provider.py', 'atlas_codex_task.py')
PINNED = {'LICENSE': 'f30a86b925d54505d3cb15c5f5ebcce1c556020636d6611aa9ecdede4a6ec842',
          'LICENSE-Plip': '987261e3f86324df894a1668cf7b9ba0cd797cb381d33e883f75240a2321a4ee',
          'requirements-windows-lock.txt': 'ecf1bdcc542ffa4c22891bd30a8167c8cedd370a65e1e8995ba0449bdcd795df'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_files(root):
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Invalid packaging input directory.')
    for p in root.rglob('*'):
        if p.is_symlink():
            raise ValueError('Symlink packaging input refused.')
        if p.is_file():
            if p.name.lower() in STATE or p.suffix.lower() in ('.pem', '.pfx', '.key', '.pdb'):
                raise ValueError('Private state or debug material in packaging input: ' + p.name)
            yield p
        elif not p.is_dir():
            raise ValueError('Non-regular packaging input refused.')


def regular(path):
    if path.is_symlink() or not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError('Non-regular direct input refused.')


def notice_path(root, name):
    rel = Path(name)
    if rel.is_absolute() or '..' in rel.parts or '\\' in name:
        raise ValueError('Unsafe notice path.')
    return root / rel


def validate(build, notices):
    config = json.loads((build / 'Atticus.runtimeconfig.json').read_text())
    frameworks = {p['name']: p['version'] for p in config['runtimeOptions']['includedFrameworks']}
    for name in ('Microsoft.NETCore.App', 'Microsoft.WindowsDesktop.App'):
        if frameworks.get(name) != '10.0.14':
            raise ValueError('Unreviewed .NET runtime version.')
    reviewed = {}
    dot = notices / 'dotnet-10.0.14'
    dm = json.loads((dot / 'manifest.json').read_text())
    reviewed.update({k.lower(): v['version'] for k, v in dm['packages'].items()})
    expected = [(notice_path(dot, x['file']), x['sha256']) for x in dm['notices']]
    expected.append((notice_path(dot, dm['additional_license']['file']), dm['additional_license']['sha256']))
    nuget = notices / 'nuget-ci3'
    nm = json.loads((nuget / 'manifest.json').read_text())
    for package in nm['packages']:
        reviewed[package['id'].lower()] = package['version']
        expected.extend((notice_path(nuget, x['file']), x['sha256']) for x in package['extracted'])
    expected.extend((notice_path(nuget, x['file']), x['sha256']) for x in nm['exact_source_supplements'])
    for path, sha in expected:
        if not path.is_file() or path.is_symlink() or digest(path) != sha:
            raise ValueError('Notice missing or changed: ' + path.name)
    deps = json.loads((build / 'Atticus.deps.json').read_text())
    required = {'runtimepack.microsoft.netcore.app.runtime.win-x64',
                'runtimepack.microsoft.windowsdesktop.app.runtime.win-x64',
                'runtimepack.microsoft.windows.sdk.net.ref', 'microsoft.web.webview2',
                'naudio', 'system.speech', 'whisper.net'}
    if not required.issubset({s.split('/')[0].lower() for s in deps['libraries']}):
        raise ValueError('Incomplete dependency inventory.')
    for name, entry in deps['libraries'].items():
        if entry['type'] not in ('package', 'runtimepack'):
            continue
        package, version = name.split('/', 1)
        package = package.removeprefix('runtimepack.').lower()
        if reviewed.get(package) != version:
            raise ValueError('Unreviewed dependency: ' + name)


def stage(build, source, notices, plip, output, receipt):
    build, source, notices, plip, output = map(Path, (build, source, notices, plip, output))
    if output.exists() or output.is_symlink():
        raise ValueError('Output must be new.')
    for root in (build, source, notices):
        if root.is_symlink() or not root.is_dir():
            raise ValueError('Invalid input directory.')
    for path, key in ((source / 'LICENSE', 'LICENSE'), (plip, 'LICENSE-Plip'),
                      (source / 'requirements-windows-lock.txt', 'requirements-windows-lock.txt')):
        regular(path)
        if digest(path) != PINNED[key]:
            raise ValueError('Direct input differs from reviewed version: ' + key)
    files = list(safe_files(build))
    regular(Path(receipt))
    hashes = json.loads(Path(receipt).read_text())
    if hashes != {p.relative_to(build).as_posix(): digest(p) for p in files}:
        raise ValueError('Build differs from supplied CI output receipt.')
    exe = (build / 'Atticus.exe').read_bytes()
    if len(exe) < 64 or exe[:2] != b'MZ':
        raise ValueError('Application is not a PE executable.')
    offset = struct.unpack_from('<I', exe, 60)[0]
    if exe[offset:offset+6] != b'PE\0\0\x64\x86':
        raise ValueError('Application is not Windows x64 PE.')
    validate(build, notices)
    if not (build / 'Atticus.exe').is_file():
        raise ValueError('Compiled application missing.')
    inputs = list(safe_files(build)) + list(safe_files(notices))
    if any(p.name.lower().startswith(('python', 'vcruntime140')) for p in safe_files(build)):
        raise ValueError('External-Python package cannot contain Python/runtime DLLs.')
    for name in MODULES:
        if not (source / name).is_file() or (source / name).is_symlink():
            raise ValueError('Required source module missing.')
    if not plip.is_file() or not plip.read_bytes():
        raise ValueError('Plip attribution missing.')
    # Validate all source subdirectories before creating output.
    for folder in ('ui', 'integrations'):
        list(safe_files(source / folder))
    output.mkdir(parents=True)
    for root, dest in ((build, output), (notices, output / 'licenses')):
        for p in safe_files(root):
            target = dest / p.relative_to(root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, target)
    for name in MODULES:
        shutil.copyfile(source / name, output / name)
    for folder, extensions in (('integrations', {'.py'}), ('ui', {'.html', '.js', '.ico', '.png'})):
        (output / folder).mkdir()
        for p in sorted((source / folder).glob('*')):
            if p.is_file() and p.suffix in extensions:
                shutil.copyfile(p, output / folder / p.name)
    shutil.copyfile(source / 'LICENSE', output / 'LICENSE-ATTICUS.txt')
    shutil.copyfile(plip, output / 'LICENSE-Plip.txt')
    shutil.copyfile(source / 'requirements-windows-lock.txt', output / 'requirements-windows-lock.txt')
    shutil.copyfile(Path(__file__).with_name('windows_first_run.py'), output / 'Setup-Windows.py')
    (output / 'Setup-Windows.cmd').write_text(
        '@echo off\r\ncd /d "%~dp0"\r\npy -3.13 "%~dp0Setup-Windows.py"\r\n'
        'if errorlevel 1 echo Setup failed. See README.txt; existing files were preserved.\r\npause\r\n', encoding='ascii')
    (output / 'README.txt').write_text(
        'ATLAS Windows x64 EXPERIMENTAL - SETUP REQUIRED\n\n'
        'This is a Windows preview, not feature parity with the Mac app.\n'
        'Headless CI does not verify microphone, tray, onboarding, approvals or normal conversation.\n'
        'Codex tasks remain disabled. No foreground Terra/API parity is claimed.\n\n'
        '1. Extract this whole folder to a new location; preserve any older installation.\n'
        '2. Install official 64-bit Python 3.13.17 or a newer 3.13 patch, including Python Launcher:\n'
        '   https://www.python.org/downloads/windows/\n'
        '3. Double-click Setup-Windows.cmd. Review the location, then type SETUP.\n'
        '   It creates %LOCALAPPDATA%\\ATLAS\\venv and downloads exact hash-locked dependencies.\n'
        '   Nothing is installed until you confirm. Network access to official PyPI is required.\n'
        '   Existing runtimes are preserved, not replaced. On failure, review the incomplete runtime.\n'
        '4. Ensure Microsoft WebView2 Runtime is installed using Microsoft instructions:\n'
        '   https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution\n'
        '5. Open Atticus.exe (the retained internal executable name). Review any Windows warning;\n'
        '   this preview is not publisher-signed. Do not disable security protections.\n'
        '   Claude Code installation/sign-in, when needed, is separate and owner-controlled:\n'
        '   https://code.claude.com/docs/en/setup\n\n'
        'No Python interpreter or its VC runtime DLLs are redistributed in this package.\n'
        'The app includes self-contained .NET components and exact notices under licenses/.\n'
        'Keep LICENSE-ATTICUS.txt and LICENSE-Plip.txt with the application.\n'
        'No automatic updater, login startup, credential transfer or permission grants are performed by setup.\n'
        'Rollback: quit this preview and reopen your preserved older copy. User settings are separate\n'
        'under %APPDATA%\\ATLAS; runtime/models are under %LOCALAPPDATA%\\ATLAS.\n'
        'Do not delete these folders unless you explicitly intend to remove their contents.\n', encoding='utf-8')
    manifest = {p.relative_to(output).as_posix(): digest(p) for p in safe_files(output)}
    (output / 'MANIFEST.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for arg in ('build', 'source', 'notices', 'plip', 'output', 'receipt'):
        parser.add_argument('--' + arg, required=True)
    stage(**vars(parser.parse_args()))
