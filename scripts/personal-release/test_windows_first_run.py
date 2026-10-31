import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('first', Path(__file__).with_name('windows_first_run.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class FirstRun(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.lock = self.path / 'requirements.txt'
        self.lock.write_text('mss==9.0.2 --hash=sha256:' + 'a' * 64 + '\n')
        self.base = self.path / 'local' / 'ATLAS'

    def test_cancel_has_no_effect(self):
        self.assertFalse(m.install(self.base, self.lock, confirm=lambda _: ''))
        self.assertFalse(self.base.exists())

    def test_success_exact_hashes_and_no_global_config(self):
        calls = []
        with patch.dict(m.os.environ, {'PIP_EXTRA_INDEX_URL': 'https://untrusted.invalid', 'PYTHONPATH': 'bad'}):
            self.assertTrue(m.install(self.base, self.lock, confirm=lambda _: 'SETUP',
                create=lambda p: p.mkdir(), run=lambda *a, **k: calls.append((a, k))))
        args, kwargs = calls[0]
        self.assertIn('--require-hashes', args[0])
        self.assertIn('--only-binary=:all:', args[0])
        self.assertNotIn('PIP_EXTRA_INDEX_URL', kwargs['env'])
        self.assertNotIn('PYTHONPATH', kwargs['env'])
        self.assertTrue((self.base / 'runtime-setup-receipt.txt').exists())
        self.assertFalse((self.base / '.runtime-setup.lock').exists())

    def test_offline_failure_preserved_and_retry_refused(self):
        def fail(*a, **k):
            raise subprocess.CalledProcessError(1, 'synthetic offline')
        with self.assertRaises(subprocess.CalledProcessError):
            m.install(self.base, self.lock, confirm=lambda _: 'SETUP', create=lambda p: p.mkdir(), run=fail)
        self.assertTrue((self.base / '.runtime-setup.lock').exists())
        with self.assertRaises(ValueError):
            m.install(self.base, self.lock, confirm=lambda _: self.fail('must not prompt'))

    def test_invalid_lock_refused(self):
        self.lock.write_text('--extra-index-url https://untrusted.invalid\n')
        with self.assertRaises(ValueError):
            m.install(self.base, self.lock)

    def test_confirmation_cannot_swap_pip_input(self):
        original = self.lock.read_bytes()
        def confirm(_):
            self.lock.write_text('--index-url https://untrusted.invalid/simple\n')
            return 'SETUP'
        def run(args, **kwargs):
            if '-r' in args:
                path = Path(args[args.index('-r') + 1])
                self.assertNotEqual(path, self.lock)
                self.assertEqual(path.read_bytes(), original)
        self.assertTrue(m.install(self.base, self.lock, confirm=confirm,
                                 create=lambda p: p.mkdir(), run=run))

    def test_existing_runtime_preserved(self):
        (self.base / 'venv').mkdir(parents=True)
        marker = self.base / 'venv' / 'keep'
        marker.write_text('safe')
        with self.assertRaises(ValueError):
            m.install(self.base, self.lock)
        self.assertEqual(marker.read_text(), 'safe')

    def test_symlink_refused(self):
        self.base.parent.mkdir(parents=True)
        self.base.symlink_to(self.path, target_is_directory=True)
        with self.assertRaises(ValueError):
            m.install(self.base, self.lock)


if __name__ == '__main__':
    unittest.main()
