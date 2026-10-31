#!/usr/bin/env python3
"""Stage Atticus core plus explicit per-device setup; no redistributed Pi/Node code."""
import argparse,json,os,plistlib,shutil,subprocess,tempfile
from pathlib import Path
import stage
HERE=Path(__file__).resolve().parent

def package(app,out,expected,commit,sign=True):
 app=app.resolve();out=out.absolute();res=app/'Contents/Resources'
 if out.exists() or out.is_symlink():raise ValueError('Output already exists.')
 if stage.digest(app/'Contents/MacOS/Atticus')!=expected:raise ValueError('Unexpected app executable hash.')
 with open(app/'Contents/Info.plist','rb') as f:info=plistlib.load(f)
 if info.get('CFBundleIdentifier')!='com.atticus.personal.dev':raise ValueError('Unexpected app identity.')
 text=(res/'foreground_openai.py').read_text()
 if 'Application Support' not in text or 'runtime.json' not in text or 'INCOMPLETE' not in text:raise ValueError('App lacks verified external-runtime support.')
 if commit:stage.verify_sources(res,commit)
 if sign and not commit:raise ValueError('Approved source commit required.')
 with tempfile.TemporaryDirectory(prefix='atticus-core-release-',dir=out.parent) as d:
  target=Path(d,stage.bundle_filename(info));c=target/'Contents';r=c/'Resources';m=c/'MacOS';r.mkdir(parents=True);m.mkdir()
  shutil.copy2(app/'Contents/Info.plist',c/'Info.plist')
  for name in ('Atticus','PersonalKeychain'):
   source=app/'Contents/MacOS'/name
   if source.is_symlink():raise ValueError('Executable symlink refused.')
   shutil.copy2(source,m/name)
  for name in stage.PYTHON_RESOURCES:
   if (res/name).is_symlink():raise ValueError('Resource symlink refused.')
   shutil.copy2(res/name,r/name)
  shutil.copy2(res/'AppIcon.icns',r/'AppIcon.icns');(r/'ui').mkdir()
  for p in sorted((res/'ui').iterdir()):
   if p.is_file() and not p.is_symlink() and p.suffix in ('.js','.html','.icns'):shutil.copy2(p,r/'ui'/p.name)
  if commit:stage.verify_sources(r,commit)
  notices=r/'Licenses';notices.mkdir();shutil.copy2(stage.ROOT/'LICENSE',notices/'Atticus-MIT.txt');shutil.copy2(stage.ROOT/'LICENSE-Plip',notices/'Plip-MIT.txt')
  setup=r/'Setup';setup.mkdir()
  for name in ('bootstrap_runtime.py','pi-package-lock.json','Setup.command','FIRST-RUN.md'):
   if sign:
    approved=subprocess.run(['git','show',commit+':scripts/personal-release/'+name],cwd=stage.ROOT,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
    import hashlib
    if approved.returncode or hashlib.sha256(approved.stdout).hexdigest()!=stage.digest(HERE/name):raise ValueError('Setup file differs from approved commit: '+name)
   shutil.copy2(HERE/name,setup/name)
  os.chmod(setup/'Setup.command',0o755)
  manifest={'format':1,'runtime':'external-user-installed','bundle_id':info['CFBundleIdentifier'],'source_commit':commit,'input_executable_sha256':expected,'minimum_macos':'26.0','architecture':'arm64','redistributed_runtime_packages':[], 'files':[{'path':p.relative_to(target).as_posix(),'sha256':stage.digest(p)} for p in sorted(target.rglob('*')) if p.is_file() and p!=m/'Atticus']}
  (r/'release-manifest.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n')
  if sign:
   subprocess.run(['/usr/bin/lipo',str(m/'Atticus'),'-verify_arch','arm64'],check=True,capture_output=True)
   subprocess.run(['/usr/bin/codesign','--force','--sign','-',str(target)],check=True,capture_output=True)
   subprocess.run(['/usr/bin/codesign','--verify','--deep','--strict',str(target)],check=True,capture_output=True)
  zipfile=Path(d,'bundle.zip');stage.zip_tree(target,zipfile);os.chmod(zipfile,0o600);os.link(zipfile,out)
 return {'zip_sha256':stage.digest(out),'runtime':'external-user-installed'}
def main():
 p=argparse.ArgumentParser();p.add_argument('--app',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--expected-executable-sha256',required=True);p.add_argument('--source-commit',required=True);a=p.parse_args()
 try:print(json.dumps(package(a.app,a.output,a.expected_executable_sha256,a.source_commit)))
 except (ValueError,OSError,subprocess.SubprocessError) as e:raise SystemExit('Core staging failed: '+str(e))
if __name__=='__main__':main()
