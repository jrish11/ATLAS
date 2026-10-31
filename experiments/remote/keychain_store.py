"""Explicit-use interface for Atticus Dev's isolated macOS Keychain helper."""
import json
import os
import subprocess

class KeychainError(Exception): pass

class KeychainStore:
    def __init__(self, helper, runner=subprocess.run, slot='custom-server'):
        if not os.path.isabs(helper): raise ValueError('Keychain helper must use an absolute path.')
        if slot not in ('custom-server', 'openai-codex', 'foreground-openai'): raise ValueError('Unsupported Keychain slot.')
        self.helper, self.runner, self.slot = helper, runner, slot

    def _call(self, action, secret=None):
        request = {'action': action, 'slot': self.slot}
        if secret is not None: request['secret'] = secret
        try:
            result = self.runner([self.helper], input=json.dumps(request), capture_output=True, text=True, timeout=30)
            data = json.loads(result.stdout)
        except (OSError, subprocess.TimeoutExpired, ValueError) as e:
            raise KeychainError('Keychain operation failed.') from e
        if not isinstance(data, dict) or not data.get('ok'):
            if action == 'get' and isinstance(data, dict) and data.get('missing'): return None
            raise KeychainError('Keychain operation was denied or failed.')
        return data.get('secret') if action == 'get' else None

    def get(self): return self._call('get')
    def set(self, value):
        if not isinstance(value, str) or not value or len(value.encode()) > 16000: raise ValueError('Invalid secret.')
        return self._call('set', value)
    def delete(self): return self._call('delete')


class ProviderKeyStore:
    """Profile marker plus Keychain value. Never write a new secret into JSON."""
    def __init__(self, directory, backend, slot='custom-server'):
        fields = {'custom-server': ('apiKey', 'apiKeyConfigured'), 'openai-codex': ('codexApiKey', 'codexApiKeyConfigured'), 'foreground-openai': ('foregroundOpenAIKey', 'foregroundOpenAIKeyConfigured')}
        if slot not in fields: raise ValueError('Unsupported provider slot.')
        self.directory, self.backend = directory, backend
        self.legacy_field, self.marker = fields[slot]

    def _read(self):
        path = os.path.join(self.directory, 'settings.json')
        try:
            with open(path, 'rb') as f: raw = f.read()
        except FileNotFoundError:
            self._snapshot = None; return {}
        self._snapshot = raw
        data = json.loads(raw)
        if not isinstance(data, dict): raise KeychainError('Settings are invalid.')
        return data

    def _write(self, data):
        import tempfile
        if any(data.get(k) for k in ('apiKey', 'codexApiKey', 'foregroundOpenAIKey')): raise KeychainError('Refusing to write a plaintext provider key.')
        data.pop('apiKey', None); data.pop('codexApiKey', None); data.pop('foregroundOpenAIKey', None)
        fd, path = tempfile.mkstemp(prefix='.key-settings-', dir=self.directory)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush(); os.fsync(f.fileno())
            current = os.path.join(self.directory, 'settings.json')
            try:
                with open(current, 'rb') as f: latest = f.read()
            except FileNotFoundError: latest = None
            if latest != self._snapshot: raise KeychainError('Settings changed; the existing file was preserved.')
            os.replace(path, current)
        finally:
            if os.path.exists(path): os.unlink(path)

    def _locked(self, fn):
        import fcntl
        os.makedirs(self.directory, mode=0o700, exist_ok=True)
        with open(os.path.join(self.directory, 'provider-key.lock'), 'a') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            return fn()

    def set(self, secret):
        def operation():
            data = self._read()
            if any(data.get(k) for k in ('apiKey', 'codexApiKey')): raise KeychainError('A legacy plaintext key requires explicit migration first.')
            self.backend.set(secret)
            data[self.marker] = True
            self._write(data)
        return self._locked(operation)

    def set_and_select(self, secret, confirmed=False):
        """Save a user-entered Codex key and select its mode in one settings write."""
        if confirmed is not True: raise KeychainError('Explicit confirmation is required.')
        if self.legacy_field != 'codexApiKey': raise KeychainError('This action requires the Codex slot.')
        def operation():
            data = self._read()
            if any(data.get(k) for k in ('apiKey', 'codexApiKey')): raise KeychainError('A legacy plaintext key requires explicit migration first.')
            self.backend.set(secret)
            data[self.marker] = True
            data['codexAuthMode'] = 'api_key'
            self._write(data)
        return self._locked(operation)

    def set_foreground_and_select(self, secret, confirmed=False):
        """Explicitly configure the separate text-only OpenAI foreground path."""
        if confirmed is not True: raise KeychainError('Explicit confirmation is required.')
        if self.legacy_field != 'foregroundOpenAIKey': raise KeychainError('This action requires the foreground OpenAI slot.')
        def operation():
            data = self._read()
            if any(data.get(k) for k in ('apiKey', 'codexApiKey', 'foregroundOpenAIKey')): raise KeychainError('A legacy plaintext key requires explicit migration first.')
            self.backend.set(secret)
            data[self.marker] = True
            data['client'] = 'pi'
            data['foregroundProvider'] = 'openai'
            data['foregroundModel'] = 'gpt-6.1-terra'
            self._write(data)
        return self._locked(operation)

    def select_foreground_model(self, model, confirmed=False):
        """Change only the configured foreground model, without accessing Keychain."""
        if confirmed is not True or self.legacy_field != 'foregroundOpenAIKey':
            raise KeychainError('Explicit foreground confirmation is required.')
        if model != 'gpt-6.1-terra':
            raise KeychainError('Unsupported foreground model.')
        def operation():
            data = self._read()
            if data.get(self.marker) is not True or data.get('client') != 'pi' or data.get('foregroundProvider') != 'openai':
                raise KeychainError('Foreground OpenAI is not configured.')
            data['foregroundModel'] = model
            self._write(data)
        return self._locked(operation)

    def get(self):
        data = self._read()
        if data.get(self.legacy_field): raise KeychainError('A legacy plaintext key requires explicit migration first.')
        if data.get(self.marker) is not True: return None
        value = self.backend.get()
        if not isinstance(value, str) or not value: raise KeychainError('The configured Keychain key is unavailable.')
        return value

    def discard_legacy(self, confirmed=False):
        if confirmed is not True: raise KeychainError('Explicit confirmation is required.')
        def operation():
            data = self._read()
            if not data.get(self.legacy_field): raise KeychainError('No legacy key is available.')
            data.pop(self.legacy_field, None)
            self._write(data)
        return self._locked(operation)

    def delete(self):
        def operation():
            data = self._read()
            if any(data.get(k) for k in ('apiKey', 'codexApiKey')): raise KeychainError('A legacy plaintext key requires explicit migration first.')
            self.backend.delete()
            data[self.marker] = False
            self._write(data)
        return self._locked(operation)

    def resolve_both(self, confirmed=False, *, migrate=False, other_backend=None):
        if confirmed is not True: raise KeychainError('Explicit confirmation is required.')
        def operation():
            data = self._read()
            keys = [('apiKey', 'apiKeyConfigured', self.backend if self.legacy_field == 'apiKey' else other_backend),
                    ('codexApiKey', 'codexApiKeyConfigured', self.backend if self.legacy_field == 'codexApiKey' else other_backend)]
            if not all(isinstance(data.get(field), str) and data[field] for field, _, _ in keys):
                raise KeychainError('Both legacy keys are required for this action.')
            if migrate:
                if any(backend is None for _, _, backend in keys): raise KeychainError('Keychain backend unavailable.')
                for field, marker, backend in keys:
                    backend.set(data[field]); data[marker] = True
            for field, _, _ in keys: data.pop(field, None)
            self._write(data)
        return self._locked(operation)

    def migrate(self, confirmed=False):
        if confirmed is not True: raise KeychainError('Explicit confirmation is required for migration.')
        def operation():
            data = self._read()
            secret = data.get(self.legacy_field)
            if not isinstance(secret, str) or not secret: raise KeychainError('No legacy key is available to migrate.')
            other = 'codexApiKey' if self.legacy_field == 'apiKey' else 'apiKey'
            if data.get(other): raise KeychainError('Remove or migrate the other plaintext key first.')
            self.backend.set(secret)
            data.pop(self.legacy_field, None)
            data[self.marker] = True
            self._write(data)
        return self._locked(operation)


if __name__ == '__main__':
    import sys
    try:
        request = json.load(sys.stdin)
        directory = os.environ['ATTICUS_DIR']
        helper = os.environ['ATTICUS_DEV_KEYCHAIN_HELPER']
        slot = request.get('slot', 'custom-server')
        store = ProviderKeyStore(directory, KeychainStore(helper, slot=slot), slot=slot)
        action = request.get('action')
        if action == 'set': store.set(request.get('secret'))
        elif action == 'set-and-select': store.set_and_select(request.get('secret'), request.get('confirmed') is True)
        elif action == 'set-foreground-and-select': store.set_foreground_and_select(request.get('secret'), request.get('confirmed') is True)
        elif action == 'select-foreground-model': store.select_foreground_model(request.get('model'), request.get('confirmed') is True)
        elif action == 'delete': store.delete()
        elif action == 'migrate': store.migrate(request.get('confirmed') is True)
        elif action == 'discard-legacy': store.discard_legacy(request.get('confirmed') is True)
        elif action in ('migrate-both', 'discard-both'):
            other_slot = 'openai-codex' if slot == 'custom-server' else 'custom-server'
            store.resolve_both(request.get('confirmed') is True, migrate=action == 'migrate-both',
                               other_backend=KeychainStore(helper, slot=other_slot))
        else: raise KeychainError('Unsupported action.')
        print(json.dumps({'ok': True}))
    except (KeychainError, KeyError, OSError, ValueError, TypeError):
        print(json.dumps({'ok': False, 'error': 'Keychain operation failed or requires migration.'}))
        sys.exit(1)
