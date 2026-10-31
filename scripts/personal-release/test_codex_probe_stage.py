import importlib.util
from pathlib import Path
import tarfile
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('stage', Path(__file__).with_name('stage_codex_probe_package.py'))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


class ProbeStageTests(unittest.TestCase):
    def test_normal_members(self):
        m.validate_members([tarfile.TarInfo('bin/codex.exe'), tarfile.TarInfo('codex-package.json')])

    def test_unsafe_names_and_links(self):
        for name in ('../outside', '/absolute', 'C:/absolute', 'bin\\outside'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                m.validate_members([tarfile.TarInfo(name)])
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE):
            member = tarfile.TarInfo('link'); member.type = kind
            with self.subTest(kind=kind), self.assertRaises(ValueError): m.validate_members([member])

    def test_case_collisions(self):
        with self.assertRaises(ValueError):
            m.validate_members([tarfile.TarInfo('BIN/Codex.exe'), tarfile.TarInfo('bin/codex.exe')])

    def test_changed_archive_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as temp:
            archive, out = Path(temp) / 'fixture.tar.gz', Path(temp) / 'output'
            archive.write_bytes(b'synthetic wrong hash')
            with self.assertRaises(ValueError): m.stage(archive, out)
            self.assertFalse(out.exists())


if __name__ == '__main__': unittest.main()
