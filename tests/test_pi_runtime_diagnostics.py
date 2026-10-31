import hashlib, json, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import foreground_openai as f

class RuntimeDiagnostics(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.home=Path(self.temp.name);self.profile=str(self.home/'.config/atticus-personal-dev');self.runtime=self.home/'Library/Application Support/Atticus Dev/pi-runtime';self.module=patch.object(f,'__file__',str(self.home/'app/foreground_openai.py'));self.module.start();self.addCleanup(self.module.stop)
 def diag(self):return f.diagnose_runtime(self.profile,str(self.home))
 def prepare(self):
  self.runtime.mkdir(parents=True,exist_ok=True);self.node=self.home/'vendor/node';self.node.parent.mkdir(exist_ok=True);self.node.write_bytes(b'fixture');self.node.chmod(0o755);self.descriptor=self.runtime/'runtime.json';self.descriptor.write_text(json.dumps({'node_path':str(self.node),'node_sha256':hashlib.sha256(b'fixture').hexdigest()}))
  package=self.runtime/'node_modules/@earendil-works/pi-coding-agent';(package/'dist/bundle').mkdir(parents=True);(package/'dist/bundle/cli.js').write_text('fixture');(package/'dist/bundle/cli.js').chmod(0o755);(package/'package.json').write_text(json.dumps({'name':'@earendil-works/pi-coding-agent','version':'1.4.0'}));binary=self.runtime/'node_modules/.bin/pi';binary.parent.mkdir();binary.symlink_to(package/'dist/bundle/cli.js');self.package=package;self.binary=binary
 def test_missing_incomplete_descriptor_node_and_package_reasons(self):
  self.assertEqual(self.diag()['reason'],'runtime_missing');self.runtime.mkdir(parents=True);(self.runtime/'INCOMPLETE').touch();self.assertEqual(self.diag()['reason'],'runtime_incomplete');(self.runtime/'INCOMPLETE').unlink();self.assertEqual(self.diag()['reason'],'descriptor_missing');self.descriptor=self.runtime/'runtime.json';self.descriptor.write_text('{}');self.assertEqual(self.diag()['reason'],'descriptor_invalid')
  self.prepare();self.assertEqual(self.diag(),{'ready':True,'reason':'ready','runtime_kind':'per_device'});self.node.write_bytes(b'changed');self.assertEqual(self.diag()['reason'],'node_changed');self.node.unlink();self.assertEqual(self.diag()['reason'],'node_missing')
 def test_setup_entries_require_owner_confirmation_and_dev_bundle(self):
  root=Path(__file__).resolve().parents[1];swift=(root/'Atticus.swift').read_text();onboarding=(root/'ui/onboarding.html').read_text();settings=(root/'ui/settings.html').read_text()
  code=swift.split('func openPiRuntimeSetup()',1)[1].split('// First-run window',1)[0]
  self.assertIn('com.atticus.personal.dev',code);self.assertIn('alert.runModal() == .alertFirstButtonReturn',code);self.assertIn('Setup/Setup.command',code);self.assertIn("setupPiRuntime",onboarding);self.assertIn("setupPiRuntime",settings)

 def test_package_and_binary_mismatch_never_return_paths(self):
  self.prepare();self.package.joinpath('package.json').write_text('{}');self.assertEqual(self.diag()['reason'],'package_mismatch');self.package.joinpath('package.json').write_text(json.dumps({'name':'@earendil-works/pi-coding-agent','version':'1.4.0'}));self.binary.unlink();self.assertEqual(self.diag()['reason'],'binary_mismatch');self.assertNotIn(str(self.home),json.dumps(self.diag()))
