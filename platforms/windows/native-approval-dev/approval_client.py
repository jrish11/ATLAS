"""Experimental private-pipe client for a native approval host.

Not imported by the shipping request path. It never creates an approval and
never reads a grant from the filesystem or an environment variable.
"""
import hashlib
import json
import os
import queue
import threading
import time
import uuid

MAX_LINE = 16384


class ApprovalError(Exception):
    pass


def _read_line(reader, timeout):
    result = queue.Queue(maxsize=1)
    def read_one():
        try: result.put(reader.readline(MAX_LINE + 1))
        except Exception: result.put(None)
    threading.Thread(target=read_one, daemon=True).start()
    try: return result.get(timeout=timeout)
    except queue.Empty: return None


class ApprovalClient:
    def __init__(self, reader, writer, session, task, project, scope, clock=time.time, timeout=30):
        if not all(isinstance(x, str) and x for x in (session, task, project, scope)):
            raise ValueError('A native-approved session, task, project, and scope are required.')
        self.reader, self.writer = reader, writer
        self.session, self.task, self.project, self.scope = session, task, project, scope
        if not 0 < timeout <= 30: raise ValueError("Timeout must be within 30 seconds.")
        self.clock, self.timeout, self.closed = clock, timeout, False

    @classmethod
    def from_host(cls, reader, writer, expected_task, expected_project, clock=time.time, timeout=30):
        # Host sends this only over its inherited anonymous pipe. The child
        # refuses a context that differs from the task/project it was given.
        raw = _read_line(reader, timeout)
        if not raw or len(raw) > MAX_LINE or not raw.endswith(b'\n'):
            raise ApprovalError('Native approval context unavailable.')
        try: hello = json.loads(raw)
        except (TypeError, ValueError, UnicodeError) as exc: raise ApprovalError('Invalid native approval context.') from exc
        if (not isinstance(hello, dict) or hello.get('task') != expected_task or
                hello.get('project') != expected_project or hello.get('scope') != 'workspace-write; network-disabled'):
            raise ApprovalError('Native approval context does not match the request.')
        return cls(reader, writer, hello.get('session'), expected_task, expected_project, hello['scope'], clock, timeout)

    def decide(self, operation):
        if self.closed or not isinstance(operation, dict): return 'cancel'
        payload = json.dumps(operation, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
        if len(payload.encode('utf-8')) > 8192: return 'cancel'
        nonce = uuid.uuid4().hex
        digest = hashlib.sha256(payload.encode('utf-8')).hexdigest()
        request = {'session':self.session, 'nonce':nonce, 'task':self.task, 'project':self.project,
                   'scope':self.scope, 'payload':payload, 'digest':digest}
        try:
            encoded = (json.dumps(request, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')
            if len(encoded) > MAX_LINE: return 'cancel'
            self.writer.write(encoded); self.writer.flush()
            raw = _read_line(self.reader, self.timeout)
            if raw is None:
                self.closed = True
                return 'cancel'
            if not raw or len(raw) > MAX_LINE or not raw.endswith(b'\n'): return 'cancel'
            response = json.loads(raw)
            if not isinstance(response, dict): return 'cancel'
            if any(response.get(k) != v for k, v in {'session':self.session, 'nonce':nonce, 'digest':digest}.items()): return 'cancel'
            expiry = response.get('expiresUnixMs')
            if type(expiry) is not int or self.clock() * 1000 >= expiry: return 'cancel'
            return response.get('decision') if response.get('decision') in ('accept', 'decline') else 'cancel'
        except (OSError, ValueError, TypeError, UnicodeError):
            return 'cancel'

    def codex_handler(self, request):
        """Adapter for CodexProvider's already-correlated approval callback."""
        if not isinstance(request, dict) or request.get('method') not in (
                'item/commandExecution/requestApproval', 'item/fileChange/requestApproval'):
            return 'cancel'
        params = request.get('params')
        if not isinstance(params, dict) or not all(isinstance(params.get(k), str) and params[k] for k in ('threadId', 'turnId')):
            return 'cancel'
        return self.decide(request)

    def close(self):
        self.closed = True


def windows_inherited_streams(read_handle, write_handle):
    """Open explicitly inherited anonymous handles and make them non-inheritable.

    Windows-only. The caller must close both streams; no child should inherit
    them. This function has not been verified on native Windows.
    """
    if os.name != 'nt': raise ApprovalError('Windows is required.')
    import msvcrt
    rfd = msvcrt.open_osfhandle(int(read_handle), os.O_RDONLY | os.O_BINARY)
    try:
        wfd = msvcrt.open_osfhandle(int(write_handle), os.O_WRONLY | os.O_BINARY)
    except Exception:
        os.close(rfd)
        raise
    try:
        os.set_inheritable(rfd, False); os.set_inheritable(wfd, False)
        return os.fdopen(rfd, 'rb', buffering=0), os.fdopen(wfd, 'wb', buffering=0)
    except Exception:
        os.close(rfd); os.close(wfd)
        raise
