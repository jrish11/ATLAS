import importlib.util,json,os,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock
HERE=Path(__file__).resolve().parent;spec=importlib.util.spec_from_file_location('release_bootstrap',HERE/'bootstrap_runtime.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
class BootstrapTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.node=self.root/'node';self.node.write_text('fixture');self.node.chmod(0o700);self.npm=self.root/'npm-cli.js';self.npm.write_text('fixture');self.out=self.root/'runtime';self.calls=[]
 def runner(self,args,**kw):
  self.calls.append((args,kw))
  if args[-1]=='--version':return subprocess.CompletedProcess(args,0,stdout='v22.23.1\n')
  out=Path(kw['cwd']);package=out/'node_modules/@earendil-works/pi-coding-agent';(package/'dist/bundle').mkdir(parents=True)
  (package/'package.json').write_text(json.dumps({'name':'@earendil-works/pi-coding-agent','version':'1.4.0'}));(package/'dist/bundle/cli.js').write_text('fixture')
  bindir=out/'node_modules/.bin';bindir.mkdir();(bindir/'pi').symlink_to('../@earendil-works/pi-coding-agent/dist/bundle/cli.js')
  return subprocess.CompletedProcess(args,0,stdout='')
 def test_confirmed_setup_uses_isolated_npm_and_no_scripts(self):
  result=b.install(self.out,self.node,self.npm,confirmed=True,runner=self.runner)
  self.assertEqual(result['status'],'installed');self.assertFalse((self.out/'INCOMPLETE').exists());self.assertEqual(json.loads((self.out/'runtime.json').read_text())['node_path'],str(self.node.resolve()))
  args,kw=self.calls[-1];self.assertIn('--ignore-scripts',args);self.assertIn('--no-audit',args);self.assertNotIn('OPENAI_API_KEY',kw['env']);self.assertEqual(kw['cwd'],self.out)
 def test_cancel_and_existing_output_cause_no_install(self):
  with self.assertRaisesRegex(ValueError,'confirmation|confirm-download'):b.install(self.out,self.node,self.npm,runner=self.runner)
  self.assertFalse(self.out.exists());self.out.mkdir()
  with self.assertRaisesRegex(ValueError,'new absolute'):b.install(self.out,self.node,self.npm,confirmed=True,runner=self.runner)
  self.assertFalse(self.calls)
 def test_lockfile_rejects_non_registry_and_missing_integrity(self):
  lock=json.loads((HERE/'pi-package-lock.json').read_text());self.assertTrue(b.validate_lock(lock));name=next(x for x in lock['packages'] if x)
  lock['packages'][name]['resolved']='https://example.org/private';
  with self.assertRaisesRegex(ValueError,'public npm'):b.validate_lock(lock)
 def test_failed_install_leaves_explicit_incomplete_marker(self):
  def failed(args,**kwargs):
   if args[-1]=='--version':return subprocess.CompletedProcess(args,0,stdout='v22.23.1\n')
   raise subprocess.CalledProcessError(1,args)
  with self.assertRaises(subprocess.CalledProcessError):b.install(self.out,self.node,self.npm,confirmed=True,runner=failed)
  self.assertTrue((self.out/'INCOMPLETE').exists())
if __name__=='__main__':unittest.main()
