"""Opt-in, no-account scratch probe for a locally supplied pinned Codex CLI.

Does not download, install, modify global settings, or contact an API. It runs
one built-in Windows cmd inside Codex's explicitly selected MXC sandbox and
checks scratch writes inside and outside the project. Network isolation and
model/approval behavior are NOT tested. Intended only for an isolated CI VM.
"""
import argparse
import hashlib
import os
import pathlib
import subprocess
import tempfile

PIN = '9d563ee4e0441ff9d59d612013e0460ddf8e5709735c2d9f6b98b7ef8ca4eb42'


def digest_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as src:
        for chunk in iter(lambda: src.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def run(executable):
    if os.name != 'nt':
        raise RuntimeError('Windows is required')
    executable = pathlib.Path(executable).resolve(strict=True)
    if not executable.is_file() or executable.suffix.lower() != '.exe' or digest_file(executable) != PIN:
        raise RuntimeError('The supplied executable does not match the pinned official release')
    windows = pathlib.Path(os.environ['SystemRoot']).resolve(strict=True)
    system32 = windows / 'System32'
    command = system32 / 'cmd.exe'
    with tempfile.TemporaryDirectory(prefix='atlas-mxc-probe-') as temporary:
        root = pathlib.Path(temporary)
        workspace, outside, profile = root / 'project', root / 'outside', root / 'profile'
        for folder in (workspace, outside, profile, profile / 'appdata', profile / 'local'):
            folder.mkdir()
        outside_file = outside / 'must-not-be-written.txt'
        # The only paths interpolated are randomly created local scratch paths.
        if any(c in str(root) for c in '%!&|<>^\r\n'):
            raise RuntimeError('Scratch path is not safe for the command interpreter')
        script = workspace / 'fixture.cmd'
        script.write_text('@echo off\r\necho inside>"%~dp0inside.txt"\r\nif errorlevel 1 exit /b 11\r\necho outside>"' + str(outside_file) + '"\r\nif not errorlevel 1 exit /b 12\r\nexit /b 0\r\n', encoding='ascii')
        env = {'SystemRoot': str(windows), 'WINDIR': str(windows), 'PATH': str(system32),
               'USERPROFILE': str(profile), 'APPDATA': str(profile / 'appdata'),
               'LOCALAPPDATA': str(profile / 'local'), 'TEMP': str(root), 'TMP': str(root),
               'CODEX_HOME': str(profile / '.codex')}
        result = subprocess.run([str(executable), '-c', 'windows.sandbox="mxc"', 'sandbox',
                                 '--include-managed-config', '--permission-profile', ':workspace',
                                 '--', str(command), '/d', '/c', str(script)], cwd=str(workspace),
                                env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=30, check=False)
        if result.returncode != 0 or not (workspace / 'inside.txt').is_file() or outside_file.exists():
            raise RuntimeError('MXC scratch write-boundary probe did not pass (exit %s)' % result.returncode)
    return 'MXC scratch write-boundary probe passed; network and full isolation remain unverified.'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable', help='Locally supplied official pinned Codex x64 executable')
    print(run(parser.parse_args().executable))
