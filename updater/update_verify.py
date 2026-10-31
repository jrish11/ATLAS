"""Fail-closed update verification/staging. No network, installation or key creation.

Only the trusted native updater may supply a pinned-signature verifier and a
platform bundle verifier. Neither is configurable through a model/settings file.
"""
import base64
import datetime as dt
import hashlib
import io
import json
import os
import plistlib
import re
import shutil
import stat
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

REPOSITORY = 'jrish11/ATLAS'
BUNDLE_ID = 'com.atticus.personal.dev'
MAX_ARCHIVE = 256 * 1024 * 1024
MAX_EXPANDED = 512 * 1024 * 1024
MAX_FILES = 5000
MAX_MANIFEST = 256 * 1024
MAX_MEMBER = 128 * 1024 * 1024
DISALLOWED = {'settings.json', 'me.json', 'auth.json', 'credentials.json', '.env', '.npmrc', '.netrc'}

class UpdateRejected(ValueError):
    pass

def reject(message):
    raise UpdateRejected(message)

def strict_json(data, maximum=MAX_MANIFEST):
    if not isinstance(data, bytes) or not 0 < len(data) <= maximum:
        reject('Invalid metadata size.')
    def pairs(rows):
        result = {}
        for key, value in rows:
            if key in result:
                reject('Duplicate metadata field.')
            result[key] = value
        return result
    try:
        return json.loads(data.decode('utf-8'), object_pairs_hook=pairs,
                          parse_constant=lambda _: reject('Nonfinite metadata value.'))
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        reject('Malformed update metadata.')

def fields(value, expected):
    if type(value) is not dict or set(value) != set(expected):
        reject('Unsupported metadata fields.')

def version(value):
    if type(value) is not str or len(value)>40 or not re.fullmatch(r'v(0|[1-9]\d*)\.(0|[1-9]\d*)(?:\.(0|[1-9]\d*))?', value):
        reject('Invalid release version.')
    numbers = tuple(int(x) for x in value[1:].split('.'))
    return numbers + (0,) * (3-len(numbers))

def os_version(value):
    if type(value) is not str or len(value)>40 or not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)(?:\.(0|[1-9]\d*))?', value):
        reject('Invalid OS version.')
    return version('v'+value)

def timestamp(value):
    if type(value) is not str or not re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ', value):
        reject('Invalid release time.')
    try:
        return dt.datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=dt.timezone.utc)
    except ValueError:
        reject('Invalid release time.')

@dataclass(frozen=True)
class VerifiedRelease:
    version: str
    sequence: int
    update_epoch: int
    build: int
    channel: str
    url: str
    sha256: str
    size: int
    minimum_macos: str
    architecture: str
    changelog: str
    manifest_sha256: str

def verify_manifest(raw, signature_raw, *, pinned_verify=None, now, current_version,
                    highest_sequence, current_epoch, current_build, machine, macos,
                    allow_prerelease=False):
    """Verify exact manifest bytes before parsing authority-bearing fields.

    pinned_verify(key_id, signature64, raw_bytes) must use an embedded trust root.
    The empty/default configuration rejects every update. No fallback to hashes.
    """
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_MANIFEST:
        reject('Invalid metadata size.')
    envelope = strict_json(signature_raw, 2048)
    fields(envelope, ('key_id', 'algorithm', 'signature'))
    if envelope['algorithm'] != 'Ed25519' or type(envelope['key_id']) is not str or not re.fullmatch(r'[a-z0-9-]{1,64}', envelope['key_id']):
        reject('Unsupported signing identity.')
    try:
        signature = base64.b64decode(envelope['signature'], validate=True)
    except (ValueError, TypeError):
        reject('Malformed signature.')
    if len(signature) != 64 or pinned_verify is None:
        reject('Release signing is not configured.')
    try:
        accepted = pinned_verify(envelope['key_id'], signature, raw)
    except Exception:
        reject('Signature verification failed.')
    if accepted is not True:
        reject('Untrusted release signature.')
    data = strict_json(raw)
    fields(data, ('schema', 'product', 'repository', 'version', 'sequence', 'channel', 'update_epoch', 'build',
                  'published_at', 'expires_at', 'minimum_macos', 'architecture',
                  'bundle_id', 'archive', 'changelog'))
    if type(data['schema']) is not int or data['schema'] != 2 or data['product'] != 'ATLAS' or data['repository'] != REPOSITORY or data['bundle_id'] != BUNDLE_ID:
        reject('Wrong update identity.')
    # Epoch is publisher-signed migration authority; display labels are not builds.
    # An epoch increase permits the explicitly branded 3.x -> 1.1 transition,
    # while build and feed sequence remain globally increasing and never reset.
    for number in (data['update_epoch'], data['build'], current_epoch, current_build):
        if type(number) is not int or not 0 <= number <= 2**53-1:
            reject('Invalid internal update order.')
    if data['update_epoch'] < current_epoch or data['build'] <= current_build:
        reject('Internal build rollback.')
    remote_version, installed_version = version(data['version']), version(current_version)
    if data['update_epoch'] == current_epoch and remote_version < installed_version:
        reject('Display downgrade needs a signed epoch transition.')
    if type(data['sequence']) is not int or type(highest_sequence) is not int or not 0 <= highest_sequence < data['sequence'] <= 2**53-1:
        reject('Release rollback or invalid sequence.')
    if data['channel'] not in ('stable', 'prerelease') or (data['channel'] == 'prerelease' and allow_prerelease is not True):
        reject('Release channel not enabled.')
    if data['architecture'] not in ('arm64', 'x86_64') or data['architecture'] != machine:
        reject('Incompatible architecture.')
    if os_version(data['minimum_macos']) > os_version(macos):
        reject('Newer macOS required.')
    if not isinstance(now, dt.datetime) or now.tzinfo is None:
        reject('Trusted current time required.')
    published, expires = timestamp(data['published_at']), timestamp(data['expires_at'])
    if published > now + dt.timedelta(minutes=5) or not published < expires <= published + dt.timedelta(days=90) or now >= expires:
        reject('Expired or invalid release time.')
    if type(data['changelog']) is not str or not 1 <= len(data['changelog']) <= 32000 or any(ord(c)<32 and c not in '\n\t' for c in data['changelog']):
        reject('Invalid changelog.')
    archive = data['archive']; fields(archive, ('url', 'sha256', 'size'))
    asset = 'ATLAS-'+data['version']+'-macOS-'+machine+'-PUBLIC.zip'
    expected = 'https://github.com/'+REPOSITORY+'/releases/download/'+data['version']+'/'+asset
    if archive['url'] != expected or urlsplit(archive['url']).netloc != 'github.com':
        reject('Unapproved download origin or asset.')
    if type(archive['sha256']) is not str or not re.fullmatch(r'[0-9a-f]{64}', archive['sha256']):
        reject('Invalid archive hash.')
    if type(archive['size']) is not int or not 0 < archive['size'] <= MAX_ARCHIVE:
        reject('Invalid archive size.')
    return VerifiedRelease(data['version'], data['sequence'], data['update_epoch'], data['build'], data['channel'], archive['url'],
                           archive['sha256'], archive['size'], data['minimum_macos'],
                           machine, data['changelog'], hashlib.sha256(raw).hexdigest())

def archive_bytes(path, release):
    """Take one bounded immutable snapshot; don't hash then reopen an attacker path."""
    if type(release.size) is not int or not 0<release.size<=MAX_ARCHIVE:
        reject('Invalid archive size.')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        meta = os.fstat(fd)
        if not stat.S_ISREG(meta.st_mode) or meta.st_size != release.size:
            reject('Archive size/type changed.')
        with os.fdopen(fd, 'rb', closefd=False) as handle:
            data = handle.read(release.size+1)
    finally:
        os.close(fd)
    if len(data) != release.size or hashlib.sha256(data).hexdigest() != release.sha256:
        reject('Archive hash changed.')
    return data

def inspect_archive(data):
    """Inspect all names/types/expanded sizes before a single member is written."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        infos = archive.infolist()
        if not 1 <= len(infos) <= MAX_FILES:
            reject('Archive entry limit.')
        seen, files, expanded = {}, set(), 0
        for item in infos:
            raw = item.orig_filename
            if raw != item.filename or any(ord(c)<32 or ord(c)==127 for c in raw) or '\\' in raw or ':' in raw or raw.startswith('/'):
                reject('Unsafe archive name.')
            name = raw[:-1] if raw.endswith('/') else raw
            parts = name.split('/')
            if any(p in ('', '.', '..') for p in parts) or unicodedata.normalize('NFC', name) != name:
                reject('Unsafe archive path.')
            if parts[0] not in ('ATLAS.app', 'READ-ME-FIRST.md', 'PUBLIC-RELEASE.json') or (parts[0] != 'ATLAS.app' and len(parts)!=1):
                reject('Unexpected archive root.')
            kind = stat.S_IFMT(item.external_attr >> 16)
            if item.flag_bits & 1 or kind not in (0, stat.S_IFREG, stat.S_IFDIR) or (kind == stat.S_IFDIR) != item.is_dir() and kind != 0:
                reject('Archive link, encryption or special entry.')
            key = name.casefold()
            if key in seen or any('/'.join(parts[:n]).casefold() in files for n in range(1,len(parts))):
                reject('Duplicate or conflicting archive path.')
            if not item.is_dir() and any(k.startswith(key+'/') for k in seen):
                reject('File/directory archive conflict.')
            seen[key] = name
            if not item.is_dir():
                files.add(key)
            if any(p.lower() in DISALLOWED or p.lower().endswith(('.key','.pem','.p12','.pfx','.log','.jsonl','.sqlite','.db')) for p in parts):
                reject('State or credentials in update.')
            expanded += item.file_size
            if item.file_size > MAX_MEMBER or expanded > MAX_EXPANDED or item.compress_type not in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED):
                reject('Archive expansion limit or compression.')
        required = {'atlas.app/contents/info.plist','atlas.app/contents/macos/atticus',
                    'atlas.app/contents/macos/personalkeychain',
                    'atlas.app/contents/resources/licenses/atticus-mit.txt',
                    'atlas.app/contents/resources/licenses/plip-mit.txt'}
        if not required <= files:
            reject('Incomplete app archive.')
        return archive
    except (zipfile.BadZipFile, UnicodeError, NotImplementedError):
        reject('Malformed app archive.')

def stage_archive(path, release, destination, *, verify_bundle=None):
    """Stage into a NEW private directory, never touch an installed app/profile.

    verify_bundle must independently enforce code signature, embedded trust,
    architecture/minimum OS and no unexpected nested executable identities.
    No default verifier means no staged update is returned as usable.
    """
    if not isinstance(release, VerifiedRelease) or verify_bundle is None:
        reject('Native update verification not configured.')
    data = archive_bytes(path, release)
    archive = inspect_archive(data)
    supplied = Path(destination)
    parent = supplied.parent.resolve(strict=True)
    parent_meta = parent.stat()
    if parent_meta.st_uid != os.getuid() or parent_meta.st_mode & 0o022:
        reject('Private owned staging parent required.')
    target = parent/supplied.name
    target.mkdir(mode=0o700, parents=False, exist_ok=False)
    try:
        for item in archive.infolist():
            output = target/item.filename
            if item.is_dir():
                output.mkdir(mode=0o700, parents=True, exist_ok=True)
                continue
            output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with archive.open(item) as source, output.open('xb') as dest:
                shutil.copyfileobj(source, dest, length=1024*1024)
            executable = item.filename in ('ATLAS.app/Contents/MacOS/Atticus', 'ATLAS.app/Contents/MacOS/PersonalKeychain', 'ATLAS.app/Contents/MacOS/ATLASUpdateInstaller', 'ATLAS.app/Contents/Resources/Setup/Setup.command')
            output.chmod(0o755 if executable else 0o644)
        app = target/'ATLAS.app'
        info = plistlib.loads((app/'Contents/Info.plist').read_bytes())
        if info.get('CFBundleIdentifier') != BUNDLE_ID or info.get('CFBundleExecutable') != 'Atticus':
            reject('Staged bundle identity changed.')
        if info.get('CFBundleVersion') != str(release.build) or type(info.get('ATLASUpdateEpoch')) is not int or info['ATLASUpdateEpoch'] != release.update_epoch:
            reject('Staged internal release order changed.')
        if verify_bundle(app, release) is not True:
            reject('Native app trust validation failed.')
        return app
    except Exception:
        shutil.rmtree(target)
        raise
    finally:
        archive.close()
