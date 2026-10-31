"""CI-only unpacker for an explicitly downloaded official no-account probe tool."""
import argparse
import hashlib
from pathlib import Path, PurePosixPath
import tarfile

ARCHIVE_SHA256 = 'd559bb88e74d471265857b93b7f19bc250dae527673b9191b33534478093f6bc'
MANIFEST_SHA256 = 'b035b02d5cc8f913648a71b00df181c91a83b99753f5a0302f05e99fb485081f'
FILES = {
    'bin/codex.exe': '9d563ee4e0441ff9d59d612013e0460ddf8e5709735c2d9f6b98b7ef8ca4eb42',
    'bin/codex-code-mode-host.exe': '977c1f01c9efac0bfe1b9032717c95f92e1c965c8441a8dacbfe824c5c79a527',
    'bin/codex-exec-server.exe': 'eda5263b31e0354347e7bcdc434aff82f5c630ddba69f13449742a64e1836a37',
    'codex-path/rg.exe': '14231169855ec5205cf5a1b6f1db358ff4aed4247c86b69ce8aae647c77f6680',
    'codex-resources/codex-command-runner.exe': '5e68e3f5b4640af55db2873a0d0dc038907145708f9e735870d9279a8074c2df',
    'codex-resources/codex-windows-sandbox-setup.exe': '3995c4f57199eb8023a0f3a585f6e9fdc4d5174c22a51837aaeb15beb52954f0',
}


def digest(path):
    sha = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''): sha.update(data)
    return sha.hexdigest()


def validate_members(members):
    seen = set()
    if len(members) > 256 or sum(m.size for m in members) > 2_000_000_000:
        raise ValueError('Unexpected archive size.')
    for member in members:
        path = PurePosixPath(member.name)
        name = path.as_posix().casefold()
        if (path.is_absolute() or '..' in path.parts or ':' in member.name or '\\' in member.name
                or not (member.isdir() or member.isfile()) or name in seen):
            raise ValueError('Unsafe or duplicate archive member.')
        seen.add(name)


def stage(archive, output):
    archive, output = Path(archive), Path(output)
    if archive.is_symlink() or not archive.is_file() or output.exists() or output.is_symlink():
        raise ValueError('Require a regular archive and a new output directory.')
    if digest(archive) != ARCHIVE_SHA256:
        raise ValueError('Official archive SHA256 mismatch; nothing executed.')
    with tarfile.open(archive, 'r:gz') as package:
        validate_members(package.getmembers())
        output.mkdir(parents=True)
        package.extractall(output, filter='data')
    manifests = list(output.rglob('codex-package.json'))
    if len(manifests) != 1 or digest(manifests[0]) != MANIFEST_SHA256:
        raise ValueError('Official package manifest mismatch.')
    root = manifests[0].parent
    for relative, expected in FILES.items():
        path = root / relative
        if path.is_symlink() or not path.is_file() or digest(path) != expected:
            raise ValueError('Official helper digest mismatch: ' + relative)
    return root.resolve()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True)
    parser.add_argument('--output', required=True)
    print(stage(**vars(parser.parse_args())))
