import importlib.util
import pathlib
import tempfile
import unittest
from unittest import mock

MODULE = pathlib.Path(__file__).resolve().parents[1] / 'sandbox_probe.py'
spec = importlib.util.spec_from_file_location('sandbox_probe', MODULE)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class SandboxProbeTests(unittest.TestCase):
    def test_non_windows_refused_before_process(self):
        with mock.patch.object(probe.os, 'name', 'posix'), mock.patch.object(probe.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'Windows'):
                probe.run('missing.exe')
            run.assert_not_called()

    def test_digest_identifies_changed_bytes(self):
        with tempfile.TemporaryDirectory() as root:
            path = pathlib.Path(root) / 'fixture'
            path.write_bytes(b'fixture')
            first = probe.digest_file(path)
            path.write_bytes(b'tampered')
            self.assertNotEqual(first, probe.digest_file(path))


if __name__ == '__main__':
    unittest.main()
