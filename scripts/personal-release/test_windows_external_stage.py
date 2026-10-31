"""Synthetic staging regressions. No PE binary is ever executed."""
import importlib.util
import json
from pathlib import Path
import shutil
import struct
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('stage', Path(__file__).with_name('windows_external_stage.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
ROOT = Path(__file__).resolve().parents[2]
LOCK = '''# EXPERIMENTAL packaging candidate; not the production requirements.txt.
# CPython 3.13, Windows x64 wheels verified against PyPI release metadata.
mss==9.0.2 --hash=sha256:685fa442cc96d8d88b4eb7aadbcccca7b858e789c9259b603e1ef0e435b60425
pillow==13.0.0 --hash=sha256:9dda0788a9932776a75d8bcc020076edc308ce2508b51f6739a45e3158b3fc42
psutil==6.1.0 --hash=sha256:a8fb3752b491d246034fa4d279ff076501588ce8cbcdbb62c32fd7a377d996be
uiautomation==2.0.29 --hash=sha256:5dd51c9e77e70470142a13d903be67f256c445e7cf20b47ada0ece2bdaff9f32
comtypes==1.4.17 --hash=sha256:4e0a221dde2c589b82977bed802efd71cd5eb67a380347b732e02735e597f586
'''


class StageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.build, self.source, self.notices = [self.root / x for x in ('build', 'source', 'notices')]
        for d in (self.build, self.source, self.notices): d.mkdir()
        self.out = self.root / 'output'
        self.plip = self.root / 'LICENSE-Plip'
        shutil.copyfile(ROOT / 'LICENSE-Plip', self.plip)
        shutil.copyfile(ROOT / 'LICENSE', self.source / 'LICENSE')
        (self.source / 'requirements-windows-lock.txt').write_bytes(LOCK.encode('utf-8'))
        for name in m.MODULES: (self.source / name).write_text('# Synthetic fixture only\n')
        for name in ('ui', 'integrations'): (self.source / name).mkdir()
        pe = bytearray(80); pe[:2] = b'MZ'; struct.pack_into('<I', pe, 60, 64); pe[64:70] = b'PE\0\0\x64\x86'
        (self.build / 'Atticus.exe').write_bytes(pe)
        self.write(self.build / 'Atticus.runtimeconfig.json', {'runtimeOptions': {'includedFrameworks': [
            {'name': n, 'version': '10.0.14'} for n in ('Microsoft.NETCore.App', 'Microsoft.WindowsDesktop.App')]}})
        dot, nuget = self.notices / 'dotnet-10.0.14', self.notices / 'nuget-ci3'
        dot.mkdir(); nuget.mkdir()
        (dot / 'fixture.txt').write_text('Synthetic notice fixture only')
        sha = m.digest(dot / 'fixture.txt')
        runtime = {'microsoft.netcore.app.runtime.win-x64': '10.0.14',
                   'microsoft.windowsdesktop.app.runtime.win-x64': '10.0.14'}
        packages = {'microsoft.windows.sdk.net.ref': '10.0.19041.57', 'microsoft.web.webview2': '1.0.4258.31',
                    'naudio': '3.1.0', 'system.speech': '10.0.12', 'whisper.net': '1.9.1'}
        self.write(dot / 'manifest.json', {'packages': {k: {'version': v} for k, v in runtime.items()},
            'notices': [{'file': 'fixture.txt', 'sha256': sha}], 'additional_license': {'file': 'fixture.txt', 'sha256': sha}})
        self.write(nuget / 'manifest.json', {'packages': [{'id': k, 'version': v, 'extracted': []}
            for k, v in packages.items()], 'exact_source_supplements': []})
        libs = {('runtimepack.' + k) + '/' + v: {'type': 'runtimepack'} for k, v in runtime.items()}
        libs.update({('runtimepack.' if k == 'microsoft.windows.sdk.net.ref' else '') + k + '/' + v:
                     {'type': 'runtimepack' if k == 'microsoft.windows.sdk.net.ref' else 'package'}
                     for k, v in packages.items()})
        self.write(self.build / 'Atticus.deps.json', {'libraries': libs})
        self.receipt = self.root / 'receipt.json'
        self.refresh()

    def write(self, p, data): p.write_text(json.dumps(data))
    def refresh(self): self.write(self.receipt, {p.relative_to(self.build).as_posix(): m.digest(p) for p in self.build.rglob('*') if p.is_file()})
    def stage(self): return m.stage(self.build, self.source, self.notices, self.plip, self.out, self.receipt)
    def rejected(self):
        with self.assertRaises(ValueError): self.stage()
        self.assertFalse(self.out.exists())

    def test_synthetic_positive_and_manifest(self):
        manifest = self.stage()
        self.assertTrue(all(m.digest(self.out / p) == sha for p, sha in manifest.items()))
        self.assertFalse((self.out / 'runtime').exists())

    def test_direct_symlinks(self):
        for p in (self.source / 'LICENSE', self.source / 'requirements-windows-lock.txt', self.plip):
            original = p.read_bytes(); p.unlink(); p.symlink_to(self.build / 'Atticus.exe')
            self.rejected(); p.unlink(); p.write_bytes(original)

    def test_build_root_symlink(self):
        original = self.build; link = self.root / 'link'; link.symlink_to(original, target_is_directory=True)
        self.build = link; self.rejected()

    def test_bad_pe_even_matching_receipt(self):
        (self.build / 'Atticus.exe').write_bytes(b'NOT-A-PE-EXECUTABLE'); self.refresh(); self.rejected()

    def test_empty_inventory_even_matching_receipt(self):
        self.write(self.build / 'Atticus.deps.json', {'libraries': {}}); self.refresh(); self.rejected()

    def test_changed_build(self):
        (self.build / 'extra.dll').write_bytes(b'Synthetic changed bytes'); self.rejected()

    def test_changed_notice(self):
        (self.notices / 'dotnet-10.0.14/fixture.txt').write_text('changed'); self.rejected()

    def test_unsafe_notice_path(self):
        p = self.notices / 'dotnet-10.0.14/manifest.json'; d = json.loads(p.read_text())
        d['notices'][0]['file'] = '../outside'; self.write(p, d); self.rejected()


if __name__ == '__main__': unittest.main()
