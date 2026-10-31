import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

spec = importlib.util.spec_from_file_location('collect_python_notices', Path(__file__).resolve().parents[1] / 'collect-python-notices.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class NoticeExtractionTests(unittest.TestCase):
    def test_verified_files_are_extracted_and_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            mapping = {}
            for name, content in [('python.zip', 'python license'), ('package.whl', 'package license')]:
                path = root / name
                with ZipFile(path, 'w') as z: z.writestr('LICENSE.txt', content)
                mapping[name] = (hashlib.sha256(path.read_bytes()).hexdigest(), 'LICENSE.txt')
            with patch.object(module, 'ARTIFACTS', mapping):
                self.assertEqual(module.collect(root / 'python.zip', root, root / 'out'), ['python.zip', 'package.whl'])
                self.assertEqual((root / 'out/PYTHON.txt').read_text(), 'python license')
                self.assertIn('package license', (root / 'out/PYTHON-PACKAGES.txt').read_text())
                (root / 'package.whl').write_bytes(b'tampered')
                with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
                    module.collect(root / 'python.zip', root, root / 'bad')
                self.assertFalse((root / 'bad').exists())

if __name__ == '__main__': unittest.main()
