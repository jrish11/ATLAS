"""Read-only Codex app-server account probe; no account credentials are handled.

This adapter is intentionally separate from the Claude task runner. It cannot
start threads or turns, and never initiates sign-in or refreshes credentials.
"""
import json
import queue
import shutil
import subprocess
import threading
import time


class AccountProbeError(Exception):
    pass


class StdioTransport:
    def __init__(self, executable):
        self.messages = queue.Queue()
        try:
            self.process = subprocess.Popen([executable, 'app-server'], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding='utf-8',
                bufsize=1, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except OSError as exc:
            raise AccountProbeError('Could not start Codex app-server.') from exc
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        try:
            for line in self.process.stdout:
                try:
                    item = json.loads(line)
                    if isinstance(item, dict): self.messages.put(item)
                except (ValueError, TypeError):
                    continue
        finally:
            self.messages.put(None)

    def send(self, message):
        try:
            self.process.stdin.write(json.dumps(message) + '\n')
            self.process.stdin.flush()
        except (OSError, ValueError) as exc:
            raise AccountProbeError('Codex app-server stopped unexpectedly.') from exc

    def receive(self, timeout):
        try: message = self.messages.get(timeout=timeout)
        except queue.Empty as exc: raise AccountProbeError('Codex account check timed out.') from exc
        if message is None: raise AccountProbeError('Codex app-server stopped unexpectedly.')
        return message

    def close(self):
        try:
            self.process.terminate()
            self.process.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            try: self.process.kill(); self.process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired): pass
        finally:
            for stream in (self.process.stdin, self.process.stdout):
                if stream:
                    try: stream.close()
                    except OSError: pass


def check_account(transport_factory=None, timeout=10):
    """Return a fixed, non-identifying account status. Never return account fields."""
    if transport_factory is None:
        executable = shutil.which('codex')
        if not executable: return {'status': 'not_installed', 'text': 'Codex CLI was not found.'}
        transport_factory = lambda: StdioTransport(executable)
    transport = None
    try:
        transport = transport_factory()
        def request(identifier, method, params):
            transport.send({'id': identifier, 'method': method, 'params': params})
            deadline = time.monotonic() + timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0: raise AccountProbeError('Codex account check timed out.')
                message = transport.receive(remaining)
                # Never approve server-initiated requests during an account probe.
                if 'method' in message and 'id' in message:
                    transport.send({'id': message['id'], 'error': {'code': -32601, 'message': 'Not supported'}})
                elif message.get('id') == identifier:
                    if 'error' in message or not isinstance(message.get('result'), dict):
                        raise AccountProbeError('Codex rejected the account check.')
                    return message['result']
        request(1, 'initialize', {'clientInfo': {'name': 'atlas-windows', 'version': '0.1.0'}})
        transport.send({'method': 'initialized', 'params': {}})
        account = request(2, 'account/read', {'refreshToken': False}).get('account')
        if account is None: return {'status': 'signed_out', 'text': 'No Codex account is signed in.'}
        if not isinstance(account, dict): raise AccountProbeError('Codex returned an invalid account status.')
        if account.get('type') == 'chatgpt':
            return {'status': 'chatgpt', 'text': 'A ChatGPT account is signed in to Codex. ATLAS task integration is still in development.'}
        if account.get('type') == 'apiKey':
            return {'status': 'api_key', 'text': 'Codex is configured with an API key. ATLAS task integration is still in development.'}
        return {'status': 'unknown', 'text': 'Codex reported an unrecognized account type.'}
    except (AccountProbeError, OSError):
        return {'status': 'unavailable', 'text': 'Could not check Codex account status.'}
    finally:
        if transport is not None: transport.close()
