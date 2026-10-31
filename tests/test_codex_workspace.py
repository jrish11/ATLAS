"""Synthetic project resolution and fixed workspace checks; no user data."""
import json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import atticus,codex_provider

REQUEST='12345678-1234-4123-8123-123456789abc'

class CodexWorkspaceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir='/tmp');self.addCleanup(self.tmp.cleanup)
  self.home=Path(self.tmp.name).resolve();self.root=self.home/'.config'/'atticus-personal-dev';self.root.mkdir(parents=True)
 def proposal(self,task):return atticus.codex_workspace_proposal(str(self.root),task,REQUEST)
 def test_new_task_proposes_fixed_workspace_without_creating(self):
  result=self.proposal('Build a simple calendar')
  self.assertEqual(result['status'],'managed');self.assertEqual(result['folder'],str(self.root/'workspaces'/('task-'+REQUEST)))
  self.assertFalse((self.root/'workspaces').exists())
 def test_confirmed_alias_exact_ambiguity_and_unavailable(self):
  one=self.home/'one';two=self.home/'two';one.mkdir();two.mkdir()
  rows=[{'confirmed':True,'aliases':['cedar'], 'folder':str(one)},{'confirmed':True,'aliases':['willow'], 'folder':str(two)}]
  (self.root/'projects.json').write_text(json.dumps(rows))
  self.assertEqual(self.proposal('Use Codex on cedar')['folder'],str(one))
  self.assertEqual(self.proposal('Use Codex to fix cedar')['folder'],str(one))
  self.assertEqual(self.proposal('Use Codex to write tests for cedar')['folder'],str(one))
  self.assertEqual(self.proposal('Use Codex to write unit tests for cedar')['folder'],str(one))
  self.assertEqual(self.proposal('Build a new app for cedar')['status'],'ambiguous')
  self.assertEqual(self.proposal('Use Codex to build a new calendar inspired by cedar')['status'],'ambiguous')
  self.assertEqual(self.proposal('Build a new app like cedar')['status'],'ambiguous')
  self.assertEqual(self.proposal('Build a new app similar to cedar')['status'],'ambiguous')
  self.assertEqual(self.proposal('Create a new app using cedar as an example')['status'],'ambiguous')
  self.assertEqual(self.proposal('Use Codex to write tests for Example Project')['status'],'ambiguous')
  self.assertEqual(self.proposal('Use Codex to write unit tests for Example Project')['status'],'ambiguous')
  self.assertEqual(self.proposal('Build cedar')['status'],'ambiguous')

  self.assertEqual(self.proposal('Use Codex on cedar and willow')['status'],'ambiguous')
  self.assertEqual(self.proposal('Build an unrelated app')['status'],'managed')
  self.assertEqual(self.proposal('Fix the existing project')['status'],'ambiguous')
  self.assertEqual(self.proposal('Update my project')['status'],'ambiguous')
  self.assertEqual(self.proposal('Build a new project')['status'],'managed')
  self.assertEqual(self.proposal('Use Codex to fix my website')['status'],'ambiguous')
  self.assertEqual(self.proposal('Have Codex review Example Project')['status'],'ambiguous')
  self.assertEqual(self.proposal('build a new app unrelated to cedar')['status'],'ambiguous')
  self.assertEqual(self.proposal('use Codex on an unknown website')['status'],'ambiguous')
  one.rmdir();self.assertEqual(self.proposal('Fix cedar')['status'],'unavailable')
 def test_table_driven_conservative_scope_classification(self):
  one=self.home/'cedar';two=self.home/'willow';one.mkdir();two.mkdir()
  (self.root/'projects.json').write_text(json.dumps([{'confirmed':True,'aliases':['cedar'],'folder':str(one)},{'confirmed':True,'aliases':['willow'],'folder':str(two)}]))
  cases=[
   ('Use Codex to fix cedar','matched'),('Use Codex on project cedar','matched'),('Review cedar','matched'),('Write unit tests for cedar','matched'),
   ('Build a new calendar','managed'),('Create a new app for me','managed'),('Make a simple calculator','managed'),
   ('Build a new calendar inspired by cedar','ambiguous'),('Create a new app like cedar','ambiguous'),('Build a new site using cedar as an example','ambiguous'),
   ('Build a new app unrelated to cedar','ambiguous'),('Build a new app for cedar','ambiguous'),('Compare cedar','ambiguous'),('Fix cedar and willow','ambiguous'),
   ('Fix cedar and build a new app','ambiguous'),('Write tests for Example Project','ambiguous'),('Write integration tests for an unknown site','ambiguous'),
   ("Use Codex, don't change cedar",'ambiguous'),('Use Codex, don’t change cedar','ambiguous'),('Use Codex to never edit cedar','ambiguous'),
   ('Avoid editing cedar','ambiguous'),('Stop editing cedar','ambiguous'),('Do not fix cedar','ambiguous'),('Dont edit cedar','ambiguous'),
   ("Don't edit cedar but fix willow",'ambiguous'),('Use Codex to fix cedar','matched'),
   ('Edit cedar unless I say otherwise','ambiguous'),('Exclude cedar when editing','ambiguous'),('Fix cedar without changing tests','ambiguous'),
   ('Leave cedar alone','ambiguous'),('Never fix cedar, then update cedar','ambiguous'),('Please do not review cedar','ambiguous'),
   ("You shouldn't edit cedar",'ambiguous'),('You shouldn’t edit cedar','ambiguous'),('Do not build a new calendar','ambiguous'),
   ('Stop and review cedar','ambiguous'),('No changes to cedar','ambiguous'),('Avoid cedar and review willow','ambiguous'),
   ('Use Codex to fix my website','ambiguous'),('Have Codex review Example Project','ambiguous'),('Work on an unknown project','ambiguous'),
   ('Build a new calendar for Example Project','ambiguous'),('Build an app in an unknown repository','ambiguous'),('Cedar','ambiguous'),('Help me','ambiguous'),
  ]
  for task,expected in cases:
   with self.subTest(task=task):
    result=self.proposal(task);self.assertEqual(result['status'],expected)
    if expected=='matched':self.assertEqual(result['folder'],str(one))
 def test_bad_or_symlink_registry_does_not_fall_back(self):
  registry=self.root/'projects.json';registry.write_text('{broken')
  self.assertEqual(self.proposal('build something')['status'],'invalid')
  registry.unlink();registry.symlink_to(self.home/'outside')
  self.assertEqual(self.proposal('build something')['status'],'invalid')
 def test_fifo_registry_is_rejected_without_blocking(self):
  os.mkfifo(self.root/'projects.json')
  code='import json,sys,atticus; print(json.dumps(atticus.codex_workspace_proposal(sys.argv[1],"build a new app","12345678-1234-4123-8123-123456789abc")))'
  env={'PATH':'/usr/bin:/bin','HOME':str(self.home),'ATTICUS_DIR':str(self.root),'TMPDIR':'/tmp','PYTHONDONTWRITEBYTECODE':'1'}
  result=subprocess.run([sys.executable,'-c',code,str(self.root)],cwd=str(Path(__file__).resolve().parents[1]),env=env,capture_output=True,text=True,timeout=3)
  self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(json.loads(result.stdout)['status'],'invalid')
 def test_creation_is_fixed_and_scope_exception_is_narrow(self):
  result=atticus.create_codex_workspace(str(self.root),REQUEST);folder=Path(result['folder'])
  self.assertTrue(folder.is_dir());self.assertEqual(result['identity']['inode'],folder.stat().st_ino)
  with patch.dict(os.environ,{'HOME':str(self.home),'ATTICUS_DIR':str(self.root)}):
   self.assertEqual(codex_provider.CodexProvider.validate_scope(str(folder)),str(folder))
   with self.assertRaises(codex_provider.ProviderError):codex_provider.CodexProvider.validate_scope(str(self.root))
   with self.assertRaises(codex_provider.ProviderError):codex_provider.CodexProvider.validate_scope(str(self.root/'workspaces'))
   with self.assertRaises(codex_provider.ProviderError):codex_provider.CodexProvider.validate_scope(str(self.home))
 def test_existing_broad_workspace_permissions_are_not_changed(self):
  unsafe=self.root/'workspaces';unsafe.mkdir(mode=0o755);unsafe.chmod(0o755)
  with self.assertRaises(ValueError):atticus.create_codex_workspace(str(self.root),REQUEST)
  self.assertEqual(unsafe.stat().st_mode & 0o777,0o755);self.assertEqual(list(unsafe.iterdir()),[])
 def test_precreated_task_folder_or_symlink_never_reused(self):
  parent=self.root/'workspaces';parent.mkdir(mode=0o700)
  path=parent/('task-'+REQUEST);outside=self.home/'outside';outside.mkdir()
  path.symlink_to(outside,target_is_directory=True)
  with self.assertRaises(ValueError):atticus.create_codex_workspace(str(self.root),REQUEST)
  self.assertEqual(list(outside.iterdir()),[]);path.unlink()
  path.mkdir(mode=0o700);(path/'fixture').write_text('synthetic')
  with self.assertRaises(ValueError):atticus.create_codex_workspace(str(self.root),REQUEST)
  self.assertEqual((path/'fixture').read_text(),'synthetic')
 def test_symlinked_workspace_never_followed(self):
  outside=self.home/'outside';outside.mkdir();(self.root/'workspaces').symlink_to(outside,target_is_directory=True)
  with self.assertRaises(OSError):atticus.create_codex_workspace(str(self.root),REQUEST)
  self.assertEqual(list(outside.iterdir()),[])
 def test_untrusted_workspace_helper_cannot_create(self):
  import io
  with patch.object(atticus.sys,'argv',['atticus.py','--codex-workspace']),patch.object(atticus.sys,'stdin',io.StringIO(json.dumps({'action':'create','confirmed':True}))),patch.object(atticus,'trusted_native_context_parent',return_value=False),patch.object(atticus,'create_codex_workspace') as create,patch('builtins.print') as out:
   atticus.main();create.assert_not_called();self.assertEqual(json.loads(out.call_args.args[0])['status'],'denied')
 def test_existing_workspace_is_not_overwritten(self):
  first=atticus.create_codex_workspace(str(self.root),REQUEST);keep=Path(first['folder'])/'fixture.txt';keep.write_text('synthetic')
  with self.assertRaises(ValueError):atticus.create_codex_workspace(str(self.root),REQUEST)
  self.assertEqual(keep.read_text(),'synthetic')
 def test_native_confirmation_precedes_creation_and_dispatch(self):
  swift=(Path(__file__).resolve().parents[1]/'Atticus.swift').read_text()
  section=swift.split('    @discardableResult func startCodexRequest(',1)[1].split('    func userContentController(',1)[0]
  self.assertLess(section.index('alert.runModal()'),section.index('"action":"create"'))
  self.assertLess(section.index('"action":"create"'),section.index('sendCodexStart(confirmed)'))
  self.assertIn('createdIdentity?["device"]==device',section)
  self.assertIn('(managed && before != nil)',section)
  self.assertIn('a new ATLAS workspace will be created',section)
  helper=swift.split('    func codexWorkspaceRequest(',1)[1].split('    @discardableResult func startCodexRequest',1)[0]
  self.assertIn('done.wait(timeout:.now()+3)',helper);self.assertIn('process.terminate()',helper)
  direct=swift.split('    func run(_ t:',1)[1].split('        let point =',1)[0]
  self.assertIn('explicitCodex && !speculative && remaining == nil',direct);self.assertIn('agentsUI.startCodexRequest',direct)
  settings=(Path(__file__).resolve().parents[1]/'ui/settings.html').read_text()
  self.assertIn("$('agentsetup').hidden = other; $('codexAgentSetup').hidden = !pi;",settings)
if __name__=='__main__':unittest.main()
