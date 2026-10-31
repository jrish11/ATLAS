#!/usr/bin/env python3
"""Stage a local, sanitized development app. Never installs, launches or uploads it."""
import argparse, hashlib, json, os, plistlib, shutil, stat, subprocess, tempfile, zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
PYTHON_RESOURCES=('atticus.py','personal_commands.py','memory_destinations.py','memory_inspector.py','memory_transactions.py','memory_rules_store.py','memory_corrections.py','memory_workflows.py','memory_seed.py','folder_grants.py','foreground_openai.py','foreground_control.py','foreground_smoke.py','approval_channel.py','remote_barrier.py','remote_gate.py','remote_ipc.py','remote_loopback.py','remote_service.py','companion_registry.py','autonomy_policy.py','codex_provider.py','vault_journal.py','keychain_store.py')
SKIP={'examples','example','tests','test','__tests__','fixtures','.git','__pycache__','docs','doc'}
SENSITIVE={'auth.json','settings.json','credentials.json','api_key.json','apikey.json','token.json','tokens.json','session.json','keychain.json','.env','.npmrc','.netrc','.ds_store'}
def bundle_filename(info):
 # Display-only rename approved for this fork; never use an arbitrary plist path.
 return 'ATLAS.app' if info.get('CFBundleDisplayName',info.get('CFBundleName'))=='ATLAS' else 'Atticus Dev.app'
def digest(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
def safe_tree(root):
 root=root.resolve()
 for base,dirs,files in os.walk(root,followlinks=False):
  dirs[:]=sorted(x for x in dirs if x.lower() not in SKIP)
  for name in sorted(dirs+files):
   path=Path(base,name);relative=path.relative_to(root)
   if name.lower() in SENSITIVE or name.lower().startswith('.env') or name.lower().endswith(('.pem','.key','.p12','.pfx','.log','.jsonl','.sqlite','.sqlite3','.db')):
    raise ValueError('Sensitive or state-like file in runtime: '+str(relative))
   if path.is_symlink():
    target=os.readlink(path)
    if os.path.isabs(target) or os.path.commonpath((str(root),str(path.resolve())))!=str(root) or not path.exists():
     raise ValueError('Unsafe runtime symlink: '+str(relative))
   elif not (path.is_file() or path.is_dir()):raise ValueError('Unsupported runtime entry: '+str(relative))
def runtime_manifest(root):
    root=root.resolve();entries=[]
    for base,dirs,files in os.walk(root,followlinks=False):
        dirs[:]=sorted(x for x in dirs if x.lower() not in SKIP)
        for name in sorted(dirs+files):
            path=Path(base,name);rel=path.relative_to(root).as_posix()
            if path.is_symlink():entries.append({'path':rel,'symlink':os.readlink(path)})
            elif path.is_file():entries.append({'path':rel,'sha256':digest(path)})
    return sorted(entries,key=lambda x:x['path'])

def license_check(modules,notices):
 missing=[]; packages=[]
 for base,dirs,files in os.walk(modules,followlinks=False):
  dirs[:]=sorted(x for x in dirs if x.lower() not in SKIP and not Path(base,x).is_symlink())
  if 'package.json' not in files:continue
  with open(Path(base,'package.json'),encoding='utf-8') as f:p=json.load(f)
  name,version=p.get('name'),p.get('version')
  if not isinstance(name,str) or not isinstance(version,str):continue
  key=hashlib.sha256((name+'@'+version).encode()).hexdigest()+'.txt'
  local=next((Path(base,x) for x in sorted(files) if x.lower().startswith(('license','licence','copying'))),None)
  supplied=notices/key
  if local is None and (not supplied.is_file() or supplied.is_symlink()):missing.append(name+'@'+version)
  packages.append({'name':name,'version':version,'license':p.get('license','unknown'),'supplement':key if local is None else None})
 if missing:raise ValueError('Missing package license texts: '+', '.join(sorted(missing)))
 return sorted(packages,key=lambda x:(x['name'],x['version']))
def copy_runtime(src,dst):
 def ignore(base,names):return [x for x in names if x.lower() in SKIP]
 shutil.copytree(src,dst,symlinks=True,ignore=ignore)
def zip_tree(root,out):
 with zipfile.ZipFile(out,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for path in sorted(root.rglob('*'),key=lambda x:x.as_posix()):
   rel=path.relative_to(root.parent).as_posix(); mode=path.lstat().st_mode
   if path.is_dir() and not path.is_symlink():continue
   info=zipfile.ZipInfo(rel,(2020,1,1,0,0,0));info.create_system=3;info.external_attr=mode<<16;info.compress_type=zipfile.ZIP_DEFLATED
   if path.is_symlink():z.writestr(info,os.readlink(path).encode())
   else:
    with open(path,'rb') as source,z.open(info,'w') as dest:shutil.copyfileobj(source,dest,1024*1024)
def verify_sources(res,commit):
 if not commit or not all(c in '0123456789abcdef' for c in commit) or len(commit) not in (40,64):raise ValueError('Use a full approved source commit hash.')
 paths=[(name,res/name) for name in PYTHON_RESOURCES]+[('ui/'+p.name,p) for p in sorted((res/'ui').iterdir()) if p.is_file() and not p.is_symlink() and p.suffix in ('.html','.js','.icns')]+[('LICENSE',ROOT/'LICENSE'),('LICENSE-Plip',ROOT/'LICENSE-Plip'),('ui/AppIcon.icns',res/'AppIcon.icns')]
 for tracked,local in paths:
  result=subprocess.run(['git','show',commit+':'+tracked],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
  if result.returncode or hashlib.sha256(result.stdout).hexdigest()!=digest(local):raise ValueError('Bundle resource differs from approved source commit: '+tracked)

def stage(app,out,expected_app,node_license,notices,sign=True,expected_node=None,source_commit=None,approved_runtime=None):
 app=app.resolve(); out=out.absolute()
 if out.exists() or out.is_symlink():raise ValueError('Output already exists; refusing to overwrite.')
 exe=app/'Contents/MacOS/Atticus';helper=app/'Contents/MacOS/PersonalKeychain';res=app/'Contents/Resources';runtime=res/'pi-runtime'
 if digest(exe)!=expected_app.lower():raise ValueError('Application executable hash does not match the approved input.')
 with open(app/'Contents/Info.plist','rb') as f: info=plistlib.load(f)
 if info.get('CFBundleIdentifier')!='com.atticus.personal.dev':raise ValueError('Unexpected app identity.')
 if exe.is_symlink() or helper.is_symlink():raise ValueError('Application executables must be regular files.')
 for p in (helper,res/'foreground_openai.py',runtime/'bin/node',runtime/'node_modules/.bin/pi',node_license,ROOT/'LICENSE',ROOT/'LICENSE-Plip'):
  if not p.is_file():raise ValueError('Required input missing: '+p.name)
 if expected_node and digest(runtime/'bin/node')!=expected_node.lower():raise ValueError('Node executable hash does not match the approved input.')
 if source_commit:verify_sources(res,source_commit)
 if sign and (not expected_node or not source_commit or approved_runtime is None):raise ValueError('Release staging requires approved Node hash, source commit and runtime manifest.')
 if node_license.is_symlink() or not node_license.is_file() or node_license.stat().st_size == 0:raise ValueError('Node license must be a nonempty regular file.')
 if sign:
  subprocess.run(['/usr/bin/codesign','--verify','--deep','--strict',str(app)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
  build=subprocess.run(['/usr/bin/otool','-l',str(exe)],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True).stdout
  import re
  version=re.search(r'LC_BUILD_VERSION[\s\S]{0,160}?minos\s+(\d+)\.(\d+)',build)
  if not version or tuple(map(int,version.groups())) != (26,0):raise ValueError('Expected a macOS 26.0 deployment target.')
  version=subprocess.run([str(runtime/'bin/node'),'--version'],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=5,env={'HOME':tempfile.gettempdir(),'PATH':'/usr/bin:/bin'}).stdout.strip()
  match=re.fullmatch(r'v(\d+)\.(\d+)\.(\d+)',version)
  if not match or tuple(map(int,match.groups())) < (22,19,0):raise ValueError('Node 22.19.0 or newer is required.')
 adapter=(res/'foreground_openai.py').read_text(encoding='utf-8')
 if "os.path.dirname(__file__)" not in adapter or "'pi-runtime'" not in adapter or "'task-6'" in adapter:raise ValueError('Foreground adapter is not bundle-relative.')
 safe_tree(runtime)
 if approved_runtime is not None and runtime_manifest(runtime)!=approved_runtime:raise ValueError('Runtime does not match the approved manifest.')
 packages=license_check(runtime/'node_modules',notices)
 with open(runtime/'node_modules/@earendil-works/pi-coding-agent/package.json') as f:pi=json.load(f)
 if pi.get('version')!='1.4.0':raise ValueError('Expected Pi 1.4.0.')
 with tempfile.TemporaryDirectory(prefix='atticus-release-stage-',dir=str(out.parent)) as tmp:
  target=Path(tmp,bundle_filename(info));contents=target/'Contents';resources=contents/'Resources';mac=contents/'MacOS';resources.mkdir(parents=True);mac.mkdir()
  shutil.copy2(app/'Contents/Info.plist',contents/'Info.plist');shutil.copy2(exe,mac/'Atticus');shutil.copy2(helper,mac/'PersonalKeychain')
  for name in PYTHON_RESOURCES:
   source=res/name
   if not source.is_file() or source.is_symlink():raise ValueError('Required resource missing or symlinked: '+name)
   shutil.copy2(source,resources/name)
  shutil.copy2(res/'AppIcon.icns',resources/'AppIcon.icns')
  ui=resources/'ui';ui.mkdir()
  for source in sorted((res/'ui').iterdir()):
   if source.is_file() and not source.is_symlink() and source.suffix in ('.html','.js','.icns'):shutil.copy2(source,ui/source.name)
  if not (ui/'settings.html').is_file():raise ValueError('Settings UI missing.')
  copy_runtime(runtime,resources/'pi-runtime')
  safe_tree(resources/'pi-runtime')
  if approved_runtime is not None and runtime_manifest(resources/'pi-runtime')!=approved_runtime:raise ValueError('Copied runtime differs from approved manifest.')
  if source_commit:verify_sources(resources,source_commit)
  licenses=resources/'Licenses';licenses.mkdir();shutil.copy2(ROOT/'LICENSE',licenses/'Atticus-MIT.txt');shutil.copy2(ROOT/'LICENSE-Plip',licenses/'Plip-MIT.txt');shutil.copy2(node_license,licenses/'Node-LICENSE.txt')
  for pkg in packages:
   if pkg['supplement']:shutil.copy2(notices/pkg['supplement'],licenses/pkg['supplement'])
  if sign:
   subprocess.run(['/usr/bin/lipo',str(mac/'PersonalKeychain'),'-verify_arch','arm64'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
   subprocess.run(['/usr/bin/lipo',str(mac/'Atticus'),'-verify_arch','arm64'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
   subprocess.run(['/usr/bin/lipo',str(resources/'pi-runtime/bin/node'),'-verify_arch','arm64'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
   # Preserve the official Node binary signature and exact approved hash.
   subprocess.run(['/usr/bin/codesign','--verify','--strict',str(resources/'pi-runtime/bin/node')],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
  listing=[]
  for p in sorted(target.rglob('*')):
   if p.is_symlink():listing.append({'path':p.relative_to(target).as_posix(),'symlink':os.readlink(p)})
   elif p.is_file() and p not in (mac/'Atticus',resources/'pi-runtime/bin/node'):listing.append({'path':p.relative_to(target).as_posix(),'sha256':digest(p)})
  manifest={'format':1,'bundle_id':'com.atticus.personal.dev','input_executable_sha256':expected_app.lower(),'input_node_sha256':expected_node,'source_commit':source_commit,'pi_version':'1.4.0','packages':packages,'files':listing,'signing':'ad-hoc' if sign else 'fixture-unsigned'}
  (Path(tmp)/'manifest.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n',encoding='utf-8')
  # Manifest is inside the bundle to keep a one-app delivery.
  shutil.copy2(Path(tmp)/'manifest.json',resources/'release-manifest.json')
  if sign:
   subprocess.run(['/usr/bin/codesign','--force','--sign','-',str(target)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
   subprocess.run(['/usr/bin/codesign','--verify','--deep','--strict',str(target)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
  archive=Path(tmp,'bundle.zip');zip_tree(target,archive);os.chmod(archive,0o600)
  os.link(archive,out)  # atomic, no replacement of an existing output
 return {'zip_sha256':digest(out),'package_count':len(packages),'signing':manifest['signing']}
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--app',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--expected-executable-sha256',required=True);parser.add_argument('--node-license',type=Path,required=True);parser.add_argument('--vendor-notices',type=Path,required=True);parser.add_argument('--expected-node-sha256',required=True);parser.add_argument('--source-commit',required=True);parser.add_argument('--runtime-manifest',type=Path,required=True)
 args=parser.parse_args()
 try:print(json.dumps(stage(args.app,args.output,args.expected_executable_sha256,args.node_license,args.vendor_notices,expected_node=args.expected_node_sha256,source_commit=args.source_commit,approved_runtime=json.loads(args.runtime_manifest.read_text(encoding='utf-8')))))
 except (OSError,ValueError,KeyError,subprocess.CalledProcessError) as e:raise SystemExit('Staging failed: '+str(e))
if __name__=='__main__':main()
