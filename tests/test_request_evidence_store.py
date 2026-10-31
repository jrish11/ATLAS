"""Synthetic-only tests; REQUEST_CRYPTO_TEST_HELPER must name a test build."""
import os
import hashlib
import hmac
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

import request_evidence_store as store

HELPER = os.environ.get('REQUEST_CRYPTO_TEST_HELPER', '')
KEY = bytes(range(32))  # synthetic test key, never an owner credential


@unittest.skipUnless(HELPER and os.path.isabs(HELPER), 'synthetic CryptoKit helper not supplied')
class EncryptedEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve(); self.gate = self.root / 'agent-gates' / ('a' * 32)
        self.gate.mkdir(parents=True); self.path = self.gate / 'request'
        self.path.write_text('synthetic private request')
        self.crypto = store.CryptoHelper(HELPER)
        self.key = mock.Mock(return_value=KEY)
        self.evidence = store.EvidenceStore(str(self.root), 'a' * 32, self.crypto, self.key)

    def test_confirmed_migration_round_trip_and_record_binding(self):
        before = self.evidence.inspect(); self.assertFalse(before['sealed'])
        after = self.evidence.migrate(before['revision'], confirmed=True)
        self.assertNotEqual(before['revision'], after)
        self.assertNotIn(b'synthetic private request', self.path.read_bytes())
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        backup = self.gate / 'request.legacy-backup'
        self.assertEqual(backup.read_text(), 'synthetic private request')
        self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o600)
        self.assertEqual(self.evidence.read(), 'synthetic private request')
        other = self.root / 'agent-gates' / ('b' * 32); other.mkdir()
        (other / 'request').write_bytes(self.path.read_bytes())
        wrong_scope = store.EvidenceStore(str(self.root), 'b' * 32, self.crypto, self.key)
        with self.assertRaises(store.EvidenceError): wrong_scope.read()

    def test_cancel_and_stale_revision_never_request_key_or_change_file(self):
        revision = self.evidence.inspect()['revision']
        with self.assertRaises(store.EvidenceError): self.evidence.migrate(revision, confirmed=False)
        self.path.write_text('newer synthetic evidence')
        with self.assertRaises(store.EvidenceConflict): self.evidence.migrate(revision, confirmed=True)
        self.key.assert_not_called(); self.assertEqual(self.path.read_text(), 'newer synthetic evidence')

    def test_tamper_wrong_key_and_failed_write_fail_closed(self):
        self.evidence.migrate(self.evidence.inspect()['revision'], confirmed=True)
        original = self.path.read_bytes()
        self.key.return_value = bytes(reversed(range(32)))
        with self.assertRaises(store.EvidenceError): self.evidence.read()
        self.key.return_value = KEY
        self.path.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
        with self.assertRaises(store.EvidenceError): self.evidence.read()
        (self.gate / 'request.legacy-backup').unlink()
        self.path.write_text('synthetic private request')
        with mock.patch.object(store.os, 'replace', side_effect=OSError('synthetic failure')):
            with self.assertRaises(OSError): self.evidence.migrate(self.evidence.inspect()['revision'], confirmed=True)
        self.assertEqual(self.path.read_text(), 'synthetic private request')
        self.assertFalse(list(self.gate.glob('.request-sealed-*')))

    def test_symlinks_and_non_regular_files_are_rejected(self):
        self.path.unlink(); victim = self.gate / 'victim'; victim.write_text('unchanged')
        self.path.symlink_to(victim)
        with self.assertRaises(OSError): self.evidence.inspect()
        self.assertEqual(victim.read_text(), 'unchanged')
        self.path.unlink(); os.mkfifo(self.path)
        with self.assertRaises(store.EvidenceError): self.evidence.inspect()
        self.key.assert_not_called()

    def test_revision_bound_edit_and_denied_action(self):
        revision = self.evidence.migrate(self.evidence.inspect()['revision'], confirmed=True)
        self.key.reset_mock()
        with self.assertRaises(store.EvidenceError): self.evidence.write('changed', revision, confirmed=False)
        self.key.assert_not_called()
        updated = self.evidence.write('updated synthetic words', revision, confirmed=True)
        self.assertNotEqual(revision, updated)
        self.assertEqual(self.evidence.read(), 'updated synthetic words')
        with self.assertRaises(store.EvidenceConflict): self.evidence.write('stale', revision, confirmed=True)
        with self.assertRaises(store.EvidenceError): self.evidence.write('another edit', updated, confirmed=True)
        self.assertEqual(self.evidence.read(), 'updated synthetic words')

    def test_edit_restore_preserves_both_revisions(self):
        original = self.evidence.migrate(self.evidence.inspect()['revision'], confirmed=True)
        edited = self.evidence.write('synthetic edited words', original, confirmed=True)
        backup = self.evidence.preview_backup('edit')['revision']
        self.key.reset_mock()
        with self.assertRaises(store.EvidenceError): self.evidence.preview_sealed_backup('edit', backup)
        with self.assertRaises(store.EvidenceConflict): self.evidence.preview_sealed_backup('edit', '0' * 64, owner_authorized=True)
        self.key.assert_not_called()
        self.assertEqual(self.evidence.preview_sealed_backup('edit', backup, owner_authorized=True)['text'], 'synthetic private request')
        with self.assertRaises(store.EvidenceConflict): self.evidence.restore_edit('0' * 64, backup, confirmed=True)
        self.evidence.restore_edit(edited, backup, confirmed=True)
        self.assertEqual(self.evidence.read(), 'synthetic private request')
        displaced = self.evidence.preview_backup('sealed')['revision']
        self.evidence.recover_sealed(backup, displaced, confirmed=True)
        self.assertEqual(self.evidence.read(), 'synthetic edited words')

    def test_uncoordinated_change_during_migration_is_preserved(self):
        revision = self.evidence.inspect()['revision']
        original = self.crypto.transform
        def mutate(action, key, data, aad):
            result = original(action, key, data, aad)
            if action == 'seal': self.path.write_text('newer synthetic evidence')
            return result
        with mock.patch.object(self.crypto, 'transform', side_effect=mutate):
            with self.assertRaises(store.EvidenceConflict): self.evidence.migrate(revision, confirmed=True)
        self.assertEqual(self.path.read_text(), 'newer synthetic evidence')

    def test_post_replace_sync_failure_reports_unknown_outcome(self):
        revision = self.evidence.inspect()['revision']
        original = os.fsync
        calls = 0
        def fail_directory(fd):
            nonlocal calls
            calls += 1
            if calls == 4: raise OSError('synthetic sync failure')
            return original(fd)
        with mock.patch.object(store.os, 'fsync', side_effect=fail_directory):
            with self.assertRaisesRegex(store.EvidenceError, 'durability is unknown'):
                self.evidence.migrate(revision, confirmed=True)
        self.assertTrue(self.path.read_bytes().startswith(store.MAGIC))
        self.assertEqual(self.evidence.read(), 'synthetic private request')

    def test_hardlinks_and_changed_key_fail_before_migration(self):
        revision = self.evidence.inspect()['revision']
        self.key.side_effect = [KEY, bytes(reversed(range(32)))]
        with self.assertRaises(store.EvidenceError): self.evidence.migrate(revision, confirmed=True)
        self.assertEqual(self.path.read_text(), 'synthetic private request')
        self.assertFalse((self.gate / 'request.legacy-backup').exists())
        self.key.side_effect = None
        os.link(self.path, self.gate / 'extra-link')
        with self.assertRaises(store.EvidenceError): self.evidence.inspect()
        (self.gate / 'extra-link').unlink()
        lock = self.gate / '.request-evidence.lock'; lock.unlink()
        victim = self.gate / 'victim'; victim.write_text('untouched'); victim.chmod(0o644)
        os.link(victim, lock)
        with self.assertRaises(store.EvidenceError): self.evidence.inspect()
        self.assertEqual(stat.S_IMODE(victim.stat().st_mode), 0o644)

    def test_restore_requires_confirmation_and_both_revisions(self):
        before = self.evidence.migrate(self.evidence.inspect()['revision'], confirmed=True)
        current = self.evidence.write('synthetic edited words', before, confirmed=True)
        with self.assertRaises(store.EvidenceError): self.evidence.preview_backup('legacy')
        preview = self.evidence.preview_backup('legacy', owner_authorized=True); revision = preview['revision']
        self.assertEqual(preview['text'], 'synthetic private request')
        backup = self.gate / 'request.legacy-backup'
        with self.assertRaises(store.EvidenceError): self.evidence.restore_legacy(current, revision, confirmed=False)
        with self.assertRaises(store.EvidenceConflict): self.evidence.restore_legacy('0' * 64, revision, confirmed=True)
        self.assertTrue(self.path.read_bytes().startswith(store.MAGIC))
        self.evidence.restore_legacy(current, revision, confirmed=True)
        self.assertEqual(self.path.read_text(), 'synthetic private request')
        self.assertTrue(backup.exists())
        sealed = self.evidence.preview_backup('sealed')['revision']
        with self.assertRaises(store.EvidenceConflict): self.evidence.recover_sealed('0' * 64, sealed, confirmed=True)
        self.evidence.recover_sealed(revision, sealed, confirmed=True)
        self.assertEqual(self.evidence.read(), 'synthetic edited words')


class _SyntheticCrypto:
    """Test double for storage behavior only; never used by the application."""
    def transform(self, action, key, data, aad):
        if not isinstance(key, bytes) or len(key) != 32: raise store.EvidenceError('Invalid key')
        if action == 'seal':
            body = bytes(b ^ 0xA5 for b in data)
            return hmac.new(key, aad + body, hashlib.sha256).digest() + body
        tag, body = data[:32], data[32:]
        if not hmac.compare_digest(tag, hmac.new(key, aad + body, hashlib.sha256).digest()):
            raise store.EvidenceError('Invalid synthetic tag')
        return bytes(b ^ 0xA5 for b in body)


class SyntheticLogicTests(EncryptedEvidenceTests):
    __unittest_skip__ = False
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve(); self.gate = self.root / 'agent-gates' / ('a' * 32)
        self.gate.mkdir(parents=True); self.path = self.gate / 'request'
        self.path.write_text('synthetic private request')
        self.key = mock.Mock(return_value=KEY)
        self.crypto = _SyntheticCrypto()
        self.evidence = store.EvidenceStore(str(self.root), 'a' * 32, self.crypto, self.key)


if __name__ == '__main__': unittest.main()
