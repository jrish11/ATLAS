"""Disabled-by-default migration adapter for existing agent request evidence.

Callers must supply an already-authorized key provider and a trusted crypto
helper. This module neither provisions keys nor changes application behavior.
All writers must use this lock before any runtime integration is enabled.
"""
import base64
import contextlib
import fcntl
import hashlib
import hmac
import json
import os
import re
import secrets
import stat
import subprocess

MAGIC = b'ATLAS-REQUEST-SEALED-V1\n'
LIMIT = 512_000

class EvidenceError(Exception): pass
class EvidenceConflict(EvidenceError): pass


class CryptoHelper:
    def __init__(self, executable, runner=subprocess.run):
        if not os.path.isabs(executable): raise ValueError('Absolute helper path required.')
        self.executable, self.runner = executable, runner

    def transform(self, action, key, data, aad):
        if action not in ('seal', 'open') or not isinstance(key, bytes) or len(key) != 32:
            raise EvidenceError('Encryption key unavailable.')
        request = {'action': action, **{k: base64.b64encode(v).decode('ascii')
                   for k, v in (('key', key), ('data', data), ('aad', aad))}}
        try:
            p = self.runner([self.executable], input=json.dumps(request), capture_output=True, text=True,
                            timeout=10, env={'PATH': '/usr/bin:/bin', 'LANG': 'C'})
            obj = json.loads(p.stdout)
            if p.returncode or not isinstance(obj, dict) or set(obj) != {'ok', 'data'} or obj['ok'] is not True:
                raise EvidenceError('Evidence cryptography failed.')
            return base64.b64decode(obj['data'], validate=True)
        except (OSError, ValueError, TypeError, subprocess.SubprocessError) as e:
            raise EvidenceError('Evidence cryptography failed.') from e


class EvidenceStore:
    def __init__(self, profile_root, record_id, crypto, key_provider):
        if not os.path.isabs(profile_root) or not re.fullmatch(r'[a-f0-9]{32}', record_id):
            raise ValueError('Invalid evidence scope.')
        self.profile_root, self.record_id = os.path.abspath(profile_root), record_id
        self.crypto, self.key_provider = crypto, key_provider
        self.aad = ('atlas-request-evidence-v1:' + record_id).encode('ascii')

    @contextlib.contextmanager
    def _lock(self):
        # Existing directory only: never create or migrate owner data implicitly.
        if os.path.realpath(self.profile_root) != self.profile_root: raise EvidenceError('Invalid profile directory.')
        root = os.open(self.profile_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        gates = None
        fd = None
        lock = None
        try:
            gates = os.open('agent-gates', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
            fd = os.open(self.record_id, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=gates)
            lock = os.open('.request-evidence.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=fd)
            info = os.fstat(lock)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid():
                raise EvidenceError('Invalid evidence lock.')
            os.fchmod(lock, 0o600); fcntl.flock(lock, fcntl.LOCK_EX)
            yield fd
        finally:
            if lock is not None: os.close(lock)
            if fd is not None: os.close(fd)
            if gates is not None: os.close(gates)
            os.close(root)

    def _read_raw(self, directory_fd, name='request'):
        if name not in ('request', 'request.legacy-backup', 'request.sealed-backup', 'request.edit-backup'): raise EvidenceError('Invalid evidence name.')
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
        with os.fdopen(fd, 'rb') as f:
            info = os.fstat(f.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid():
                raise EvidenceError('Invalid evidence file.')
            raw = f.read(LIMIT + 1)
        if len(raw) > LIMIT: raise EvidenceError('Evidence is too large.')
        return raw

    def _key(self):
        try: value = self.key_provider()
        except Exception: raise EvidenceError('The evidence key is unavailable.') from None
        if not isinstance(value, bytes) or len(value) != 32: raise EvidenceError('The evidence key is unavailable.')
        return value

    def _stable_key(self):
        first, second = self._key(), self._key()
        if not hmac.compare_digest(first, second):
            raise EvidenceError('The evidence key is unavailable or changed; migration was not started.')
        return first

    def _backup(self, directory_fd, raw, name='request.legacy-backup'):
        if name not in ('request.legacy-backup', 'request.sealed-backup', 'request.edit-backup'): raise EvidenceError('Invalid backup name.')
        try:
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd)
        except FileExistsError as e: raise EvidenceError('Existing migration backup requires review.') from e
        with os.fdopen(fd, 'wb') as f:
            os.fchmod(f.fileno(), 0o600); f.write(raw); f.flush(); os.fsync(f.fileno())
        os.fsync(directory_fd)

    def _replace(self, directory_fd, raw):
        name = '.request-sealed-' + secrets.token_hex(16)
        created = False
        try:
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd)
            created = True
            with os.fdopen(fd, 'wb') as f:
                os.fchmod(f.fileno(), 0o600); f.write(raw); f.flush(); os.fsync(f.fileno())
            os.replace(name, 'request', src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
            created = False
            try: os.fsync(directory_fd)
            except OSError as e: raise EvidenceError('Replacement occurred but durability is unknown; inspect before retry.') from e
        finally:
            if created: os.unlink(name, dir_fd=directory_fd)

    def inspect(self):
        with self._lock() as fd:
            raw = self._read_raw(fd)
            return {'revision': hashlib.sha256(raw).hexdigest(), 'sealed': raw.startswith(MAGIC)}

    def migrate(self, revision, *, confirmed=False):
        if confirmed is not True: raise EvidenceError('Explicit migration confirmation required.')
        with self._lock() as fd:
            raw = self._read_raw(fd)
            if hashlib.sha256(raw).hexdigest() != revision: raise EvidenceConflict('Evidence changed.')
            if raw.startswith(MAGIC): raise EvidenceError('Evidence is already sealed.')
            try: raw.decode('utf-8')
            except UnicodeDecodeError as e: raise EvidenceError('Invalid legacy evidence.') from e
            key = self._stable_key()
            sealed = self.crypto.transform('seal', key, raw, self.aad)
            if len(sealed) + len(MAGIC) > LIMIT: raise EvidenceError('Evidence is too large.')
            # Verify before replacement; no plaintext is removed on crypto failure.
            if self.crypto.transform('open', key, sealed, self.aad) != raw: raise EvidenceError('Verification failed.')
            if self._read_raw(fd) != raw: raise EvidenceConflict('Evidence changed during migration.')
            # Preserve a private legacy copy until the owner explicitly reviews
            # recovery. Never overwrite an earlier backup automatically.
            self._backup(fd, raw)
            if self._read_raw(fd) != raw: raise EvidenceConflict('Evidence changed; review the retained migration backup.')
            self._replace(fd, MAGIC + sealed)
            return hashlib.sha256(MAGIC + sealed).hexdigest()

    def write(self, text, revision, *, confirmed=False):
        if confirmed is not True: raise EvidenceError('Explicit edit confirmation required.')
        if not isinstance(text, str) or len(text.encode('utf-8')) > LIMIT - len(MAGIC) - 28:
            raise EvidenceError('Invalid evidence.')
        with self._lock() as fd:
            raw = self._read_raw(fd)
            if hashlib.sha256(raw).hexdigest() != revision: raise EvidenceConflict('Evidence changed.')
            if not raw.startswith(MAGIC): raise EvidenceError('Legacy evidence requires explicit migration.')
            key, plain = self._key(), text.encode('utf-8')
            # Authenticate the old record as well: editing never overwrites a
            # record encrypted for another scope or with a missing/wrong key.
            self.crypto.transform('open', key, raw[len(MAGIC):], self.aad)
            sealed = self.crypto.transform('seal', key, plain, self.aad)
            if len(sealed) + len(MAGIC) > LIMIT: raise EvidenceError('Evidence is too large.')
            if self.crypto.transform('open', key, sealed, self.aad) != plain: raise EvidenceError('Verification failed.')
            if self._read_raw(fd) != raw: raise EvidenceConflict('Evidence changed during edit.')
            self._backup(fd, raw, 'request.edit-backup')
            if self._read_raw(fd) != raw: raise EvidenceConflict('Evidence changed; review the retained edit backup.')
            self._replace(fd, MAGIC + sealed)
            return hashlib.sha256(MAGIC + sealed).hexdigest()

    def read(self):
        with self._lock() as fd:
            raw = self._read_raw(fd)
            if not raw.startswith(MAGIC): raise EvidenceError('Legacy evidence requires explicit migration.')
            plain = self.crypto.transform('open', self._key(), raw[len(MAGIC):], self.aad)
            try: return plain.decode('utf-8')
            except UnicodeDecodeError as e: raise EvidenceError('Invalid evidence.') from e

    def restore_legacy(self, current_revision, backup_revision, *, confirmed=False):
        if confirmed is not True: raise EvidenceError('Explicit restore confirmation required.')
        with self._lock() as fd:
            current, backup = self._read_raw(fd), self._read_raw(fd, 'request.legacy-backup')
            if hashlib.sha256(current).hexdigest() != current_revision or hashlib.sha256(backup).hexdigest() != backup_revision:
                raise EvidenceConflict('Evidence or backup changed.')
            if not current.startswith(MAGIC) or backup.startswith(MAGIC): raise EvidenceError('Invalid restore state.')
            try: backup.decode('utf-8')
            except UnicodeDecodeError as e: raise EvidenceError('Invalid legacy backup.') from e
            if self._read_raw(fd) != current or self._read_raw(fd, 'request.legacy-backup') != backup:
                raise EvidenceConflict('Evidence or backup changed during restore.')
            self._backup(fd, current, 'request.sealed-backup')
            if self._read_raw(fd) != current or self._read_raw(fd, 'request.legacy-backup') != backup:
                raise EvidenceConflict('Evidence changed; review the retained sealed backup.')
            self._replace(fd, backup)
            return hashlib.sha256(backup).hexdigest()

    def preview_backup(self, name, *, owner_authorized=False):
        if name not in ('legacy', 'sealed', 'edit'): raise EvidenceError('Invalid backup name.')
        if name == 'legacy' and owner_authorized is not True: raise EvidenceError('Owner preview authorization required.')
        with self._lock() as fd:
            raw = self._read_raw(fd, 'request.' + name + '-backup')
            if raw.startswith(MAGIC) != (name != 'legacy'): raise EvidenceError('Invalid backup state.')
            result = {'revision': hashlib.sha256(raw).hexdigest(), 'size': len(raw), 'sealed': name != 'legacy'}
            if name == 'legacy':
                try: result['text'] = raw.decode('utf-8')
                except UnicodeDecodeError as e: raise EvidenceError('Invalid legacy backup.') from e
            return result

    def preview_sealed_backup(self, name, revision, *, owner_authorized=False):
        # This boolean is not an authorization boundary. Future integration
        # must invoke it only from a verified native owner-preview action.
        if owner_authorized is not True or name not in ('sealed', 'edit'):
            raise EvidenceError('Owner preview authorization required.')
        with self._lock() as fd:
            raw = self._read_raw(fd, 'request.' + name + '-backup')
            if hashlib.sha256(raw).hexdigest() != revision: raise EvidenceConflict('Backup changed.')
            if not raw.startswith(MAGIC): raise EvidenceError('Invalid backup state.')
            plain = self.crypto.transform('open', self._key(), raw[len(MAGIC):], self.aad)
            try: text = plain.decode('utf-8')
            except UnicodeDecodeError as e: raise EvidenceError('Invalid backup.') from e
            if self._read_raw(fd, 'request.' + name + '-backup') != raw: raise EvidenceConflict('Backup changed during preview.')
            return {'revision': revision, 'text': text}

    def recover_sealed(self, current_revision, backup_revision, *, confirmed=False):
        if confirmed is not True: raise EvidenceError('Explicit recovery confirmation required.')
        with self._lock() as fd:
            current = self._read_raw(fd)
            sealed = self._read_raw(fd, 'request.sealed-backup')
            legacy = self._read_raw(fd, 'request.legacy-backup')
            if hashlib.sha256(current).hexdigest() != current_revision or hashlib.sha256(sealed).hexdigest() != backup_revision:
                raise EvidenceConflict('Evidence or backup changed.')
            try: edit_backup = self._read_raw(fd, 'request.edit-backup')
            except FileNotFoundError: edit_backup = None
            if current not in (legacy, edit_backup) or not sealed.startswith(MAGIC):
                raise EvidenceConflict('Current evidence differs from its retained backup; review before recovery.')
            self.crypto.transform('open', self._key(), sealed[len(MAGIC):], self.aad)
            if self._read_raw(fd) != current or self._read_raw(fd, 'request.sealed-backup') != sealed:
                raise EvidenceConflict('Evidence changed during recovery.')
            self._replace(fd, sealed)
            return hashlib.sha256(sealed).hexdigest()

    def restore_edit(self, current_revision, backup_revision, *, confirmed=False):
        if confirmed is not True: raise EvidenceError('Explicit restore confirmation required.')
        with self._lock() as fd:
            current, backup = self._read_raw(fd), self._read_raw(fd, 'request.edit-backup')
            if hashlib.sha256(current).hexdigest() != current_revision or hashlib.sha256(backup).hexdigest() != backup_revision:
                raise EvidenceConflict('Evidence or backup changed.')
            if not current.startswith(MAGIC) or not backup.startswith(MAGIC): raise EvidenceError('Invalid restore state.')
            key = self._key()
            self.crypto.transform('open', key, current[len(MAGIC):], self.aad)
            self.crypto.transform('open', key, backup[len(MAGIC):], self.aad)
            self._backup(fd, current, 'request.sealed-backup')
            if self._read_raw(fd) != current or self._read_raw(fd, 'request.edit-backup') != backup:
                raise EvidenceConflict('Evidence changed; review the retained sealed backup.')
            self._replace(fd, backup)
            return hashlib.sha256(backup).hexdigest()
