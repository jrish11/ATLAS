"""Synthetic tests for the disabled encryption integration boundary."""
import hashlib
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest import mock

import atticus
import request_evidence_store as encrypted
from tests.test_request_evidence_store import KEY, _SyntheticCrypto


class RequestEvidenceIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve(); self.agent = self.root / 'agents' / ('a' * 32)
        self.agent.mkdir(parents=True)
        self.gate = self.root / 'agent-gates' / ('a' * 32); self.gate.mkdir(parents=True)
        self.request = self.gate / 'request'; self.request.write_text('synthetic original')
        self.directory = mock.patch.object(atticus, 'DIR', str(self.root)); self.directory.start(); self.addCleanup(self.directory.stop)
        self.crypto = _SyntheticCrypto()
        self.store = encrypted.EvidenceStore(str(self.root), 'a' * 32, self.crypto, lambda: KEY)

    def test_legacy_read_write_and_cleanup_are_revision_bound(self):
        self.assertEqual(atticus.read_request_evidence(str(self.request)), 'synthetic original')
        revision = hashlib.sha256(b'synthetic original').hexdigest()
        info = self.request.stat(); original_identity = (info.st_dev, info.st_ino)
        identity = atticus.write_request_evidence(str(self.request), 'synthetic newer')
        atticus.remove_request_if_unchanged(str(self.request), revision, original_identity)
        self.assertEqual(self.request.read_text(), 'synthetic newer')
        revision = hashlib.sha256(b'synthetic newer').hexdigest()
        atticus.remove_request_if_unchanged(str(self.request), revision, identity)
        self.assertFalse(self.request.exists())

    def test_identical_replacement_survives_old_cleanup(self):
        identity = atticus.write_request_evidence(str(self.request), 'same synthetic words')
        revision = hashlib.sha256(b'same synthetic words').hexdigest()
        replacement = atticus.write_request_evidence(str(self.request), 'same synthetic words')
        self.assertNotEqual(identity, replacement)
        atticus.remove_request_if_unchanged(str(self.request), revision, identity)
        self.assertEqual(self.request.read_text(), 'same synthetic words')

    def test_reserved_marker_and_oversize_do_not_replace_legacy(self):
        for invalid in ('ATLAS-REQUEST-SEALED-V1\nnot ciphertext', 'x' * 512001, '\ud800'):
            with self.subTest(case=repr(invalid[:32])):
                with self.assertRaises(OSError): atticus.write_request_evidence(str(self.request), invalid)
                self.assertEqual(self.request.read_text(), 'synthetic original')

    def test_sealed_evidence_fails_closed_and_is_not_overwritten_or_removed(self):
        revision = self.store.inspect()['revision']
        self.store.migrate(revision, confirmed=True); sealed = self.request.read_bytes()
        with self.assertRaises(atticus.SealedRequestUnavailable): atticus.read_request_evidence(str(self.request))
        with self.assertRaises(atticus.SealedRequestUnavailable): atticus.write_request_evidence(str(self.request), 'overwrite')
        atticus.remove_request_if_unchanged(str(self.request), revision, (0, 0))
        self.assertEqual(self.request.read_bytes(), sealed)
        with mock.patch.dict(os.environ, {'ATTICUS_ASK': str(self.agent), 'ATTICUS_REQUEST': 'open this in front'}, clear=True), \
             mock.patch.object(atticus, 'recent', return_value=[{'q': 'synthetic secret', 't': time.time()}]):
            self.assertFalse(atticus._request_contains('synthetic secret'))
            self.assertFalse(atticus.wants_focus())
            (self.agent / 'focus-requested').write_text('true')
            self.assertFalse(atticus.wants_focus())
        (self.gate / 'focus-requested').write_text('true')
        with mock.patch.dict(os.environ, {'ATTICUS_ASK': str(self.agent), 'ATTICUS_AGENT': '1'}, clear=True):
            self.assertFalse(atticus.wants_focus())

    def test_registered_cleanup_cannot_delete_migrated_evidence(self):
        with mock.patch.object(atticus.atexit, 'register') as register:
            atticus.save_request(str(self.agent), 'synthetic original')
        callback, path, revision, identity = register.call_args.args
        self.assertIs(callback, atticus.remove_request_if_unchanged)
        self.store.migrate(self.store.inspect()['revision'], confirmed=True)
        sealed = self.request.read_bytes(); callback(path, revision, identity)
        self.assertEqual(self.request.read_bytes(), sealed)

    def test_invalid_evidence_does_not_authorize_fallback(self):
        self.request.unlink(); self.request.symlink_to(self.gate / 'missing')
        with mock.patch.dict(os.environ, {'ATTICUS_ASK': str(self.agent), 'ATTICUS_REQUEST': 'open this in front'}, clear=True), \
             mock.patch.object(atticus, 'recent', return_value=[{'q': 'synthetic secret', 't': time.time()}]):
            self.assertFalse(atticus._request_contains('synthetic secret'))
            self.assertFalse(atticus.wants_focus())

    def test_legacy_writer_and_migration_share_the_lock(self):
        revision = self.store.inspect()['revision']; entered = threading.Event(); release = threading.Event()
        original = self.crypto.transform; outcomes = []
        def delayed(action, key, data, aad):
            if action == 'seal': entered.set(); self.assertTrue(release.wait(3))
            return original(action, key, data, aad)
        def migrate():
            try: self.store.migrate(revision, confirmed=True); outcomes.append('migrated')
            except Exception as error: outcomes.append(type(error).__name__)
        def write():
            try: atticus.write_request_evidence(str(self.request), 'unsafe overwrite'); outcomes.append('wrote')
            except atticus.SealedRequestUnavailable: outcomes.append('blocked')
        with mock.patch.object(self.crypto, 'transform', side_effect=delayed):
            first = threading.Thread(target=migrate); second = threading.Thread(target=write)
            first.start(); self.assertTrue(entered.wait(3)); second.start()
            self.assertNotIn('wrote', outcomes); release.set(); first.join(3); second.join(3)
        self.assertFalse(first.is_alive() or second.is_alive())
        self.assertEqual(outcomes, ['migrated', 'blocked'])
        self.assertEqual(self.store.read(), 'synthetic original')


if __name__ == '__main__': unittest.main()
