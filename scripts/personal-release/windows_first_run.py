"""Explicit, per-user dependency setup. No credentials, startup or security changes."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import venv

MINIMUM = (3, 13, 17)


def clean_environment():
    env = {k: v for k, v in os.environ.items()
           if not k.upper().startswith(('PIP_', 'PYTHON'))}
    env.update(PIP_CONFIG_FILE=os.devnull, PIP_DISABLE_PIP_VERSION_CHECK='1',
               PYTHONUTF8='1')
    return env


def install(base, lock, *, confirm=input, run=subprocess.run, create=None):
    """The caller supplies the user-local root; existing environments are preserved."""
    base, lock = Path(base), Path(lock)
    if not lock.is_file() or lock.is_symlink():
        raise ValueError('Missing dependency lock; extract the complete package.')
    lock_bytes = lock.read_bytes()
    text = lock_bytes.decode('utf-8')
    lines = [s.strip() for s in text.splitlines() if s.strip() and not s.startswith('#')]
    import re
    if not lines or any(not re.fullmatch(r'[A-Za-z0-9_.-]+==[0-9.]+ --hash=sha256:[0-9a-f]{64}', s) for s in lines):
        raise ValueError('Invalid dependency lock.')
    root = base / 'venv'
    if base.is_symlink() or root.exists() or root.is_symlink():
        raise ValueError('Existing runtime preserved. Review it before replacing; no files changed.')
    print('Create a private Python environment at:', root)
    print('Download only the exact hash-locked dependencies from https://pypi.org.')
    print('No sign-in, API call, permission grant, startup change or system installation.')
    if confirm('Type SETUP to continue, or press Enter to cancel: ').strip() != 'SETUP':
        return False
    base.mkdir(parents=True, exist_ok=True)
    marker = base / '.runtime-setup.lock'
    with marker.open('x', encoding='utf-8') as receipt:
        receipt.write('INCOMPLETE\n')
    try:
        if root.exists() or root.is_symlink():
            raise ValueError('Runtime appeared during setup; preserved.')
        if create is None:
            create = lambda path: venv.EnvBuilder(with_pip=True).create(path)
        create(root)
        python = root / 'Scripts' / 'python.exe'
        env = clean_environment()
        # Do not hand pip the original requirements path after the confirmation UI.
        # Only the validated frozen bytes enter the private, short-lived input file.
        with tempfile.TemporaryDirectory(prefix='atlas-locked-setup-') as scratch:
            frozen = Path(scratch) / 'requirements.txt'
            frozen.write_bytes(lock_bytes)
            run([str(python), '-I', '-m', 'pip', '--isolated', 'install',
                 '--disable-pip-version-check', '--no-input', '--no-cache-dir',
                 '--index-url', 'https://pypi.org/simple', '--only-binary=:all:',
                 '--require-hashes', '-r', str(frozen)], env=env, check=True, timeout=240)
        run([str(python), '-I', '-c',
             'import mss, PIL, psutil, uiautomation, comtypes'],
            env=env, check=True, timeout=30)
        (base / 'runtime-setup-receipt.txt').write_text(
            'Dependencies verified; lock SHA256=' + hashlib.sha256(lock_bytes).hexdigest() + '\n',
            encoding='utf-8')
        marker.unlink()
        return True
    except Exception:
        print('Setup failed. The incomplete runtime is preserved for review; no automatic retry or deletion.')
        raise


def main():
    if sys.platform != 'win32' or sys.version_info[:2] != (3, 13) or sys.version_info[:3] < MINIMUM:
        raise SystemExit('Install official 64-bit Python 3.13.17 or a newer 3.13 patch from https://www.python.org/downloads/windows/.')
    import struct
    if struct.calcsize('P') != 8:
        raise SystemExit('64-bit Python is required.')
    local = os.environ.get('LOCALAPPDATA')
    if not local or not Path(local).is_absolute():
        raise SystemExit('Windows LOCALAPPDATA is unavailable; no setup performed.')
    installed = install(Path(local) / 'ATLAS', Path(__file__).with_name('requirements-windows-lock.txt'))
    print('Setup complete. Open Atticus.exe.' if installed else 'Canceled; nothing installed.')


if __name__ == '__main__':
    main()
