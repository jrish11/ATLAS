"""Inventory exact .NET publish output and available package notices.

This gathers evidence, not legal clearance: runtime pack availability and
licenses must be reviewed against the actual published components.
"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def harvest(assets_file, deps_file, publish_dir, nuget_root, dotnet_root, output):
    assets = json.loads(Path(assets_file).read_text(encoding='utf-8'))
    deps = json.loads(Path(deps_file).read_text(encoding='utf-8'))
    publish = Path(publish_dir).resolve()
    roots = [Path(nuget_root).resolve(), (Path(dotnet_root) / 'packs').resolve()]
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    manifest = {'warning': 'Evidence only; missing notices and runtime licensing require review.',
                'runtime_target': deps.get('runtimeTarget'), 'packages': [], 'published_files': []}
    items = {}
    for collection in (assets.get('libraries', {}), deps.get('libraries', {})):
        for identifier, meta in collection.items():
            if not isinstance(meta, dict) or meta.get('type') not in ('package', 'runtimepack'): continue
            if '/' not in identifier: continue
            name, version = identifier.rsplit('/', 1)
            if not name or not version or any(c in name + version for c in '\\/:') or name in ('.', '..') or version in ('.', '..'):
                raise ValueError('Unsafe package identifier')
            items[identifier] = (name, version)
    for index, (identifier, (name, version)) in enumerate(sorted(items.items())):
        package_name = name.removeprefix('runtimepack.')
        candidates = [roots[0] / package_name.lower() / version.lower(), roots[1] / package_name / version]
        matches = [p for p in candidates if p.is_dir()]
        record = {'id': identifier, 'locations_found': len(matches), 'notice_files': []}
        for directory in matches:
            for path in sorted(directory.rglob('*')):
                if not path.is_file() or path.is_symlink(): continue
                if not any(word in path.name.lower() for word in ('license', 'licence', 'notice', 'copying')): continue
                destination = output / 'notices' / str(index) / path.relative_to(directory)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, destination)
                record['notice_files'].append({'file': destination.relative_to(output).as_posix(), 'sha256': sha(destination)})
        manifest['packages'].append(record)
    for path in sorted(publish.rglob('*')):
        if path.is_file() and not path.is_symlink():
            manifest['published_files'].append({'file': path.relative_to(publish).as_posix(), 'sha256': sha(path), 'bytes': path.stat().st_size})
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('assets', 'deps', 'publish-dir', 'nuget-root', 'dotnet-root', 'output'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    result = harvest(args.assets, args.deps, args.publish_dir, args.nuget_root, args.dotnet_root, args.output)
    missing = sum(not p['notice_files'] for p in result['packages'])
    print(f"Inventoried {len(result['packages'])} resolved package IDs and {len(result['published_files'])} published files; {missing} packages have no discovered notice. Manual review is required.")
