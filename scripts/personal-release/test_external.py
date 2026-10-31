import importlib.util,json,os,plistlib,shutil,subprocess,sys,unittest,zipfile
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import stage_external as e
import test_stage as fixtures
class ExternalPackageTests(unittest.TestCase):
 setUp=fixtures.ReleaseStageTests.setUp
 def test_approved_display_rename_preserves_private_fork_identity(self):
  info=self.app/'Contents/Info.plist';data=plistlib.loads(info.read_bytes());data.update(CFBundleDisplayName='ATLAS',CFBundleName='ATLAS');info.write_bytes(plistlib.dumps(data))
  archive=self.root/'renamed.zip';e.package(self.app,archive,self.exe,None,sign=False)
  with zipfile.ZipFile(archive) as z:
   self.assertTrue(all(x.startswith('ATLAS.app/') for x in z.namelist()))
   renamed=plistlib.loads(z.read('ATLAS.app/Contents/Info.plist'));self.assertEqual(renamed['CFBundleIdentifier'],'com.atticus.personal.dev');self.assertEqual(renamed['CFBundleExecutable'],'Atticus')
  self.assertEqual(e.stage.bundle_filename({'CFBundleDisplayName':'../../ATLAS.app'}),'Atticus Dev.app')
 def test_external_package_relocates_and_requires_explicit_setup(self):
  archive=self.root/'core.zip';e.package(self.app,archive,self.exe,None,sign=False)
  with zipfile.ZipFile(archive) as z:
   names=z.namelist();self.assertFalse(any('/pi-runtime/' in x or '/node_modules/' in x for x in names));self.assertTrue(any(x.endswith('/Setup/Setup.command') for x in names))
  relocated=self.root/'moved';relocated.mkdir();subprocess.run(['/usr/bin/ditto','-x','-k',str(archive),str(relocated)],check=True)
  resource=relocated/'Atticus Dev.app/Contents/Resources';spec=importlib.util.spec_from_file_location('external_foreground',resource/'foreground_openai.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  home=self.root/'target-home';home.mkdir();profile=home/'.config/atticus-personal-dev'
  self.assertIsNone(m.resolve_pi(str(profile),str(home)))
  runtime=home/'Library/Application Support/Atticus Dev/pi-runtime';runtime.parent.mkdir(parents=True)
  shutil.copytree(self.app/'Contents/Resources/pi-runtime',runtime,symlinks=True)
  node=self.root/'node';node.write_text('fixture node');node.chmod(0o700)
  (runtime/'runtime.json').write_text(json.dumps({'node_path':str(node),'node_sha256':e.stage.digest(node)}))
  self.assertEqual(m.resolve_pi(str(profile),str(home)),str(runtime/'node_modules/.bin/pi'))
  (runtime/'INCOMPLETE').write_text('fixture');self.assertIsNone(m.resolve_pi(str(profile),str(home)))
if __name__=='__main__':unittest.main()
