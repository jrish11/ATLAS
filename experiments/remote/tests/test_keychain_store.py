import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from keychain_store import KeychainError, KeychainStore

class KeychainTests(unittest.TestCase):
    def test_secret_goes_via_stdin_not_arguments(self):
        run = Mock(return_value=SimpleNamespace(stdout='{"ok":true}', returncode=0))
        KeychainStore('/fixture/helper', run).set('fixture-secret')
        args, kwargs = run.call_args
        self.assertEqual(args[0], ['/fixture/helper'])
        self.assertEqual(json.loads(kwargs['input'])['secret'], 'fixture-secret')
        self.assertNotIn('fixture-secret', str(args))

    def test_denial_and_missing_are_distinct(self):
        run = Mock(return_value=SimpleNamespace(stdout='{"ok":false,"missing":true}', returncode=1))
        self.assertIsNone(KeychainStore('/fixture/helper', run).get())
        run.return_value.stdout = '{"ok":false}'
        with self.assertRaises(KeychainError): KeychainStore('/fixture/helper', run).get()

    def test_codex_slot_is_distinct_and_sent_only_over_stdin(self):
        run = Mock(return_value=SimpleNamespace(stdout='{"ok":true}', returncode=0))
        KeychainStore('/fixture/helper', run, slot='openai-codex').set('fixture-codex-key')
        args, kwargs = run.call_args
        self.assertEqual(json.loads(kwargs['input'])['slot'], 'openai-codex')
        self.assertNotIn('fixture-codex-key', str(args))
        with self.assertRaises(ValueError): KeychainStore('/fixture/helper', run, slot='unknown')

    def test_empty_key_and_relative_helper_rejected(self):
        with self.assertRaises(ValueError): KeychainStore('relative')
        with self.assertRaises(ValueError): KeychainStore('/fixture/helper').set('')


class ProviderKeyStoreTests(unittest.TestCase):
    def test_new_key_never_enters_settings_and_read_uses_backend(self):
        import tempfile
        from pathlib import Path
        from keychain_store import ProviderKeyStore
        with tempfile.TemporaryDirectory() as d:
            backend=Mock(); backend.get.return_value='fixture-secret'
            store=ProviderKeyStore(d,backend); store.set('fixture-secret')
            settings=Path(d,'settings.json').read_text()
            self.assertNotIn('fixture-secret',settings)
            self.assertTrue(json.loads(settings)['apiKeyConfigured'])
            self.assertEqual(store.get(),'fixture-secret')
            store.delete(); self.assertFalse(json.loads(Path(d,'settings.json').read_text())['apiKeyConfigured'])

    def test_explicit_save_and_select_sets_mode_without_plaintext(self):
        import tempfile
        from pathlib import Path
        from keychain_store import ProviderKeyStore
        with tempfile.TemporaryDirectory() as d:
            path=Path(d,'settings.json');path.write_text('{"other":1,"codexAuthMode":"existing"}')
            backend=Mock();store=ProviderKeyStore(d,backend,slot='openai-codex')
            with self.assertRaises(KeychainError):store.set_and_select('fixture-key',False)
            backend.set.assert_not_called()
            store.set_and_select('fixture-key',True);backend.set.assert_called_once_with('fixture-key')
            data=json.loads(path.read_text());self.assertEqual(data['codexAuthMode'],'api_key');self.assertTrue(data['codexApiKeyConfigured']);self.assertEqual(data['other'],1);self.assertNotIn('fixture-key',path.read_text())
    def test_save_and_select_rejects_wrong_slot_and_reports_partial_conflict(self):
        import tempfile
        from pathlib import Path
        from keychain_store import ProviderKeyStore
        with tempfile.TemporaryDirectory() as d:
            path=Path(d,'settings.json');path.write_text('{"codexAuthMode":"existing"}')
            backend=Mock()
            with self.assertRaises(KeychainError):ProviderKeyStore(d,backend).set_and_select('fixture-key',True)
            backend.set.assert_not_called()
            backend.set.side_effect=lambda _:path.write_text('{"other":"concurrent"}')
            with self.assertRaises(KeychainError):ProviderKeyStore(d,backend,slot='openai-codex').set_and_select('fixture-key',True)
            backend.set.assert_called_once_with('fixture-key');self.assertEqual(path.read_text(),'{"other":"concurrent"}')

    def test_codex_marker_does_not_replace_custom_server_marker(self):
        import tempfile
        from pathlib import Path
        from keychain_store import ProviderKeyStore
        with tempfile.TemporaryDirectory() as d:
            path=Path(d,'settings.json'); path.write_text('{"apiKeyConfigured":true}')
            backend=Mock(); ProviderKeyStore(d,backend,slot='openai-codex').set('fixture-codex-key')
            data=json.loads(path.read_text())
            self.assertTrue(data['apiKeyConfigured']); self.assertTrue(data['codexApiKeyConfigured'])
            self.assertNotIn('fixture-codex-key',path.read_text())

    def test_legacy_migration_requires_explicit_confirmation(self):
        import tempfile
        from pathlib import Path
        from keychain_store import ProviderKeyStore
        with tempfile.TemporaryDirectory() as d:
            path=Path(d,'settings.json'); path.write_text(json.dumps({'apiKey':'fixture-legacy','other':1}))
            backend=Mock(); store=ProviderKeyStore(d,backend)
            with self.assertRaises(KeychainError): store.migrate(False)
            with self.assertRaises(KeychainError): store.set('fixture-new')
            backend.set.assert_not_called()
            self.assertEqual(json.loads(path.read_text())['apiKey'],'fixture-legacy')
            store.migrate(True)
            backend.set.assert_called_once_with('fixture-legacy')
            self.assertEqual(json.loads(path.read_text()),{'other':1,'apiKeyConfigured':True})

    def test_migration_does_not_overwrite_a_concurrent_settings_edit(self):
        import tempfile
        from pathlib import Path
        from keychain_store import ProviderKeyStore
        with tempfile.TemporaryDirectory() as d:
            path=Path(d,'settings.json'); path.write_text(json.dumps({'apiKey':'fixture-legacy'}))
            backend=Mock(); backend.set.side_effect=lambda _:path.write_text('{"other":"changed"}')
            with self.assertRaises(KeychainError): ProviderKeyStore(d,backend).migrate(True)
            self.assertEqual(path.read_text(),'{"other":"changed"}')

    def test_two_legacy_keys_require_one_explicit_batch_decision(self):
        import tempfile
        from pathlib import Path
        from keychain_store import ProviderKeyStore
        with tempfile.TemporaryDirectory() as d:
            path=Path(d,'settings.json'); original={'apiKey':'fixture-custom','codexApiKey':'fixture-codex','other':1}
            path.write_text(json.dumps(original)); custom=Mock(); codex=Mock()
            store=ProviderKeyStore(d,custom)
            with self.assertRaises(KeychainError): store.migrate(True)
            with self.assertRaises(KeychainError): store.resolve_both(False,migrate=True,other_backend=codex)
            custom.set.assert_not_called(); codex.set.assert_not_called()
            self.assertEqual(json.loads(path.read_text()),original)
            store.resolve_both(True,migrate=True,other_backend=codex)
            custom.set.assert_called_once_with('fixture-custom'); codex.set.assert_called_once_with('fixture-codex')
            self.assertEqual(json.loads(path.read_text()),{'apiKeyConfigured':True,'codexApiKeyConfigured':True,'other':1})
            self.assertNotIn('fixture-',path.read_text())

    def test_two_legacy_keys_can_be_discarded_without_keychain_calls(self):
        import tempfile
        from pathlib import Path
        from keychain_store import ProviderKeyStore
        with tempfile.TemporaryDirectory() as d:
            path=Path(d,'settings.json');path.write_text('{"apiKey":"fixture-a","codexApiKey":"fixture-b","other":1}')
            first=Mock();second=Mock()
            ProviderKeyStore(d,first).resolve_both(True,migrate=False,other_backend=second)
            self.assertEqual(json.loads(path.read_text()),{'other':1})
            first.assert_not_called(); second.assert_not_called()

    def test_failed_migration_keeps_original_file(self):
        import tempfile
        from pathlib import Path
        from keychain_store import ProviderKeyStore
        with tempfile.TemporaryDirectory() as d:
            path=Path(d,'settings.json'); original=json.dumps({'apiKey':'fixture-legacy'})
            path.write_text(original); backend=Mock(); backend.set.side_effect=KeychainError('denied')
            with self.assertRaises(KeychainError): ProviderKeyStore(d,backend).migrate(True)
            self.assertEqual(path.read_text(),original)

    def test_legacy_discard_is_explicit_and_never_calls_keychain(self):
        import tempfile
        from pathlib import Path
        from keychain_store import ProviderKeyStore
        with tempfile.TemporaryDirectory() as d:
            path=Path(d,'settings.json'); path.write_text(json.dumps({'apiKey':'fixture-legacy','other':1}))
            backend=Mock(); store=ProviderKeyStore(d,backend)
            with self.assertRaises(KeychainError): store.discard_legacy(False)
            self.assertEqual(json.loads(path.read_text())['apiKey'],'fixture-legacy')
            store.discard_legacy(True)
            self.assertEqual(json.loads(path.read_text()),{'other':1})
            backend.assert_not_called()

    def test_configured_missing_key_does_not_silently_fall_back(self):
        import tempfile
        from pathlib import Path
        from keychain_store import ProviderKeyStore
        with tempfile.TemporaryDirectory() as d:
            Path(d,'settings.json').write_text('{"apiKeyConfigured":true}')
            backend=Mock(); backend.get.return_value=None
            with self.assertRaises(KeychainError): ProviderKeyStore(d,backend).get()

    def test_atticus_provider_reads_mock_keychain_and_not_plaintext(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        import atticus
        with tempfile.TemporaryDirectory() as d:
            Path(d,'settings.json').write_text('{"apiKeyConfigured":true,"apiBase":"https://fixture.example"}')
            backend=Mock(); backend.get.return_value='fixture-secret'
            with patch.object(atticus,'DIR',d), patch.object(atticus,'PREFS',str(Path(d,'settings.json'))), \
                 patch.object(atticus.keychain_store,'KeychainStore',return_value=backend), \
                 patch.dict('os.environ',{'ATTICUS_DEV_KEYCHAIN_HELPER':'/fixture/helper'},clear=False):
                self.assertEqual(atticus.pref('apiKey',''),'fixture-secret')
                self.assertEqual(atticus.server()['ANTHROPIC_AUTH_TOKEN'],'fixture-secret')
                with patch.object(atticus,'_models_at',return_value=['fixture']) as query:
                    with patch.dict('os.environ',{'ATTICUS_PROBE_BASE':'https://fixture.example','ATTICUS_PROBE_KEY':''}):
                        self.assertEqual(atticus.models(),['fixture'])
                        self.assertEqual(query.call_args.args[1],'fixture-secret')
            self.assertNotIn('fixture-secret',Path(d,'settings.json').read_text())

if __name__ == '__main__': unittest.main()
