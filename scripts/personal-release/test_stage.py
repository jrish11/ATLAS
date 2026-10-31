import ast,hashlib,importlib.util,json,os,plistlib,subprocess,tempfile,unittest,zipfile
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
spec=importlib.util.spec_from_file_location('personal_release_stage',HERE/'stage.py');stage=importlib.util.module_from_spec(spec);spec.loader.exec_module(stage)
class ReleaseStageTests(unittest.TestCase):
 def test_all_local_runtime_imports_are_in_release_allowlist(self):
  allowed=set(stage.PYTHON_RESOURCES)
  for name in allowed:
   tree=ast.parse((ROOT/name).read_text())
   for node in ast.walk(tree):
    modules=[alias.name.split('.')[0] for alias in node.names] if isinstance(node,ast.Import) else [node.module.split('.')[0]] if isinstance(node,ast.ImportFrom) and node.module else []
    for module in modules:
     if (ROOT/(module+'.py')).is_file():self.assertIn(module+'.py',allowed,name+' has an unstaged local import')
 def test_disabled_companion_modules_are_in_release_allowlist(self):
  self.assertTrue({'remote_barrier.py','remote_gate.py','remote_ipc.py','remote_loopback.py','remote_service.py','companion_registry.py'} <= set(stage.PYTHON_RESOURCES))
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='atticus-release-fixture-');self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.app=self.root/'input.app';c=self.app/'Contents';r=c/'Resources';m=c/'MacOS';r.mkdir(parents=True);m.mkdir()
  with open(c/'Info.plist','wb') as f:plistlib.dump({'CFBundleIdentifier':'com.atticus.personal.dev','CFBundleExecutable':'Atticus'},f)
  (m/'Atticus').write_text('fake executable');(m/'Atticus').chmod(0o755);(m/'PersonalKeychain').write_text('fake helper')
  for name in stage.PYTHON_RESOURCES:(r/name).write_text('fixture')
  (r/'foreground_openai.py').write_text((ROOT/'foreground_openai.py').read_text());(r/'AppIcon.icns').write_bytes(b'fixture')
  (r/'ui').mkdir();(r/'ui'/'settings.html').write_text('fixture settings');(r/'ui'/'private.txt').write_text('PRIVATE_FIXTURE_SENTINEL');(r/'me.json').write_text('PRIVATE_FIXTURE_SENTINEL')
  runtime=r/'pi-runtime';(runtime/'bin').mkdir(parents=True);(runtime/'bin'/'node').write_text('fake node');(runtime/'bin'/'node').chmod(0o755)
  package=runtime/'node_modules/@earendil-works/pi-coding-agent';(package/'dist/bundle').mkdir(parents=True)
  (package/'package.json').write_text(json.dumps({'name':'@earendil-works/pi-coding-agent','version':'1.4.0','license':'MIT'}))
  (package/'LICENSE').write_text('fixture license');(package/'dist/bundle/cli.js').write_text('fixture cli');(package/'dist/bundle/cli.js').chmod(0o755)
  bindir=runtime/'node_modules/.bin';bindir.mkdir();(bindir/'pi').symlink_to('../@earendil-works/pi-coding-agent/dist/bundle/cli.js')
  self.node_license=self.root/'node-license';self.node_license.write_text('fixture node license');self.notices=self.root/'notices';self.notices.mkdir()
  self.exe=stage.digest(m/'Atticus');self.node=stage.digest(runtime/'bin/node')
 def package(self,out):return stage.stage(self.app,out,self.exe,self.node_license,self.notices,sign=False,expected_node=self.node)
 def test_relocation_offline_and_no_private_files(self):
  archive=self.root/'one.zip';self.package(archive)
  with zipfile.ZipFile(archive) as z:
   names=z.namelist();self.assertFalse(any(x.endswith(('me.json','private.txt')) for x in names))
   self.assertTrue(any(x.endswith('Atticus-MIT.txt') for x in names));self.assertTrue(any(x.endswith('Plip-MIT.txt') for x in names))
   self.assertFalse(any(b'PRIVATE_FIXTURE_SENTINEL' in z.read(x) for x in names))
  relocated=self.root/'relocated';relocated.mkdir();subprocess.run(['/usr/bin/ditto','-x','-k',str(archive),str(relocated)],check=True)
  res=relocated/'Atticus Dev.app/Contents/Resources';spec=importlib.util.spec_from_file_location('relocated_foreground',res/'foreground_openai.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  fakehome=self.root/'fake-home';fakehome.mkdir();resolved=module.resolve_pi(str(fakehome/'.config/atticus-personal-dev'),str(fakehome))
  self.assertEqual(resolved,str(res/'pi-runtime/node_modules/.bin/pi'));self.assertTrue(Path(resolved).is_file())
  ask=self.root/'ask';ask.mkdir();args,env=module.prepare(str(ask),'gpt-6.1-terra',{'HOME':str(fakehome),'PATH':'/usr/bin:/bin'},lambda:'fixture-key')
  self.assertIn('--no-tools',args);self.assertIn('--no-mcp',args);self.assertEqual(env['OPENAI_API_KEY'],'fixture-key');self.assertNotIn('fixture-key',(ask/'pi-profile/settings.json').read_text())
 def test_deterministic_archive_and_existing_output_protected(self):
  a=self.root/'a.zip';b=self.root/'b.zip';self.package(a);self.package(b);self.assertEqual(stage.digest(a),stage.digest(b))
  with self.assertRaisesRegex(ValueError,'already exists'):self.package(a)
 def test_missing_license_and_private_files_fail_closed(self):
  package=self.app/'Contents/Resources/pi-runtime/node_modules/@earendil-works/pi-coding-agent';(package/'LICENSE').unlink()
  with self.assertRaisesRegex(ValueError,'Missing package license'):self.package(self.root/'missing.zip')
  (package/'LICENSE').write_text('fixture');(package/'.env').write_text('fixture')
  with self.assertRaisesRegex(ValueError,'Sensitive'):self.package(self.root/'secret.zip')
 def test_external_symlink_and_wrong_node_hash_refused(self):
  runtime=self.app/'Contents/Resources/pi-runtime';(runtime/'bad').symlink_to('/tmp')
  with self.assertRaisesRegex(ValueError,'symlink'):self.package(self.root/'bad.zip')
  (runtime/'bad').unlink()
  with self.assertRaisesRegex(ValueError,'Node executable hash'):stage.stage(self.app,self.root/'wrong.zip',self.exe,self.node_license,self.notices,sign=False,expected_node='0'*64)
 def test_approved_runtime_manifest_detects_tampering(self):
  runtime=self.app/'Contents/Resources/pi-runtime';approved=stage.runtime_manifest(runtime)
  (runtime/'node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js').write_text('tampered')
  with self.assertRaisesRegex(ValueError,'approved manifest'):
   stage.stage(self.app,self.root/'tampered.zip',self.exe,self.node_license,self.notices,sign=False,expected_node=self.node,approved_runtime=approved)
 def test_external_notice_is_required_and_retained(self):
  package=self.app/'Contents/Resources/pi-runtime/node_modules/@earendil-works/pi-coding-agent';(package/'LICENSE').unlink()
  name=hashlib.sha256(b'@earendil-works/pi-coding-agent@1.4.0').hexdigest()+'.txt';(self.notices/name).write_text('fixture official notice')
  archive=self.root/'notices.zip';self.package(archive)
  with zipfile.ZipFile(archive) as z:self.assertTrue(any(x.endswith(name) for x in z.namelist()))
 def test_old_fixed_path_adapter_refused(self):
  (self.app/'Contents/Resources/foreground_openai.py').write_text("root='task-6'\n")
  with self.assertRaisesRegex(ValueError,'bundle-relative'):self.package(self.root/'old.zip')
if __name__=='__main__':unittest.main()
