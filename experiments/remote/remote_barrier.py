"""Fail-closed durable barrier for an in-flight remote task.

This records only an opaque request ID and a digest of the approved scope.  It
provides no authority to start or approve work.  Only a trusted native owner
channel may reconcile a barrier; no HTTP handler should expose clear().
"""
import hashlib
import json
import os
import re
import stat

_ID = re.compile(r'^[a-f0-9]{32}$')
_NAME = 'remote-pending.json'

class BarrierError(Exception):
    pass

class DurableBarrier:
    def __init__(self, directory):
        flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, 'O_NOFOLLOW', 0)
        self._dir = os.open(directory, flags)
        info = os.fstat(self._dir)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            os.close(self._dir)
            raise BarrierError('Unsafe barrier directory')

    def close(self):
        if self._dir is not None:
            os.close(self._dir)
            self._dir = None

    def read(self):
        try:
            fd = os.open(_NAME, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0), dir_fd=self._dir)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise BarrierError('Unreadable barrier') from exc
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077 or info.st_size > 512:
                raise BarrierError('Invalid barrier')
            data = os.read(fd, 513)
            after = os.fstat(fd)
            if len(data) > 512 or (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
                raise BarrierError('Changed barrier')
            row = json.loads(data)
            if not isinstance(row, dict) or set(row) != {'id', 'scope'} or not isinstance(row['id'], str) or not _ID.fullmatch(row['id']) or not isinstance(row['scope'], str) or not re.fullmatch(r'[a-f0-9]{64}', row['scope']):
                raise BarrierError('Invalid barrier')
            return row
        except (ValueError, UnicodeDecodeError, OSError) as exc:
            raise BarrierError('Invalid barrier') from exc
        finally:
            os.close(fd)

    def reserve(self, ident, scope):
        if not isinstance(ident, str) or not _ID.fullmatch(ident) or not isinstance(scope, dict):
            raise BarrierError('Invalid intent')
        digest = hashlib.sha256(json.dumps(scope, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        payload = json.dumps({'id': ident, 'scope': digest}, separators=(',', ':')).encode()
        try:
            fd = os.open(_NAME, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600, dir_fd=self._dir)
        except OSError as exc:
            raise BarrierError('Task requires reconciliation') from exc
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.fsync(self._dir)
        except OSError as exc:
            # Leave any partial file in place: it must block until reviewed.
            raise BarrierError('Could not persist task intent') from exc

    def clear(self, ident):
        row = self.read()
        if not row or row['id'] != ident:
            raise BarrierError('Barrier does not match')
        try:
            os.unlink(_NAME, dir_fd=self._dir)
            os.fsync(self._dir)
        except OSError as exc:
            raise BarrierError('Could not clear barrier') from exc
