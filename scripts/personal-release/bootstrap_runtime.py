#!/usr/bin/env python3
"""Explicit first-run Pi install from pinned public npm archives, without lifecycle scripts."""
import argparse,hashlib,json,os,re,shutil,subprocess,tempfile,urllib.parse
from pathlib import Path
HERE=Path(__file__).resolve().parent

def validate_lock(lock):
 if not isinstance(lock,dict) or lock.get('lockfileVersion')!=3 or not isinstance(lock.get('packages'),dict):raise ValueError('Unsupported lockfile.')
 root=lock['packages'].get('') or {}
 if root.get('dependencies')!={'@earendil-works/pi-coding-agent':'1.4.0'}:raise ValueError('Unexpected root dependency.')
 for name,row in lock['packages'].items():
  if not name:continue
  if not isinstance(name,str) or not name.startswith('node_modules/') or '..' in Path(name).parts or not isinstance(row,dict):raise ValueError('Invalid package entry.')
  url=row.get('resolved');integrity=row.get('integrity')
  if not isinstance(url,str) or not isinstance(integrity,str) or not integrity.startswith('sha512-'):raise ValueError('Unpinned package.')
  p=urllib.parse.urlsplit(url)
  if p.scheme!='https' or p.hostname!='registry.npmjs.org' or p.username or p.password or p.query or p.fragment:raise ValueError('Package source is not the public npm registry.')
 return True

def install(output,node,npm_cli,confirmed=False,runner=subprocess.run):
 if confirmed is not True:raise ValueError('Explicit --confirm-download is required.')
 if not output.is_absolute() or output.exists() or output.is_symlink():raise ValueError('Choose a new absolute runtime directory.')
 if not node.is_file() or not os.access(node,os.X_OK) or not npm_cli.is_file():raise ValueError('Provide an existing Node executable and npm CLI script.')
 lock=json.loads((HERE/'pi-package-lock.json').read_text());validate_lock(lock)
 with tempfile.TemporaryDirectory(prefix='atticus-first-run-') as d:
  temp=Path(d);(temp/'user.npmrc').write_text('');(temp/'global.npmrc').write_text('')
  env={'HOME':d,'PATH':str(node.parent)+':/usr/bin:/bin','TMPDIR':d,'NPM_CONFIG_USERCONFIG':str(temp/'user.npmrc'),
       'NPM_CONFIG_GLOBALCONFIG':str(temp/'global.npmrc'),'NPM_CONFIG_CACHE':str(temp/'cache'),'NPM_CONFIG_AUDIT':'false',
       'NPM_CONFIG_FUND':'false','NPM_CONFIG_UPDATE_NOTIFIER':'false'}
  v=runner([str(node),'--version'],capture_output=True,text=True,env=env,timeout=10,check=True).stdout.strip()
  match=re.fullmatch(r'v(\d+)\.(\d+)\.(\d+)',v)
  if not match or tuple(map(int,match.groups()))<(22,19,0):raise ValueError('Node 22.19.0 or newer is required.')
  os.mkdir(output,0o700)
  (output/'INCOMPLETE').write_text('Installation is not verified. Review before use.\n')
  (output/'package.json').write_text(json.dumps({'name':'atticus-pi-runtime','private':True,'version':'1.0.0','dependencies':{'@earendil-works/pi-coding-agent':'1.4.0'}}))
  shutil.copy2(HERE/'pi-package-lock.json',output/'package-lock.json')
  # Explicit invocation, isolated npm config/cache, no lifecycle scripts or global install.
  runner([str(node),str(npm_cli),'ci','--ignore-scripts','--omit=dev','--no-audit','--no-fund','--registry=https://registry.npmjs.org/'],cwd=output,env=env,timeout=600,check=True)
  package=output/'node_modules/@earendil-works/pi-coding-agent';binary=output/'node_modules/.bin/pi';expected=package/'dist/bundle/cli.js'
  meta=json.loads((package/'package.json').read_text())
  if meta.get('name')!='@earendil-works/pi-coding-agent' or meta.get('version')!='1.4.0' or binary.resolve()!=expected.resolve() or not expected.is_file():raise ValueError('Installed Pi layout was not verified.')
  digest=hashlib.sha256()
  with open(node,'rb') as f:
   for block in iter(lambda:f.read(1024*1024),b''):digest.update(block)
  descriptor={'node_path':str(node.resolve()),'node_sha256':digest.hexdigest()}
  fd=os.open(output/'runtime.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
  with os.fdopen(fd,'w') as f:json.dump(descriptor,f);f.flush();os.fsync(f.fileno())
  (output/'INCOMPLETE').unlink()
 return {'status':'installed','pi_version':'1.4.0','node_version':v,'note':'Atticus must be configured to use this per-device runtime; no app settings were changed.'}

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--node',type=Path,required=True);p.add_argument('--npm-cli',type=Path,required=True);p.add_argument('--confirm-download',action='store_true');a=p.parse_args()
 try:print(json.dumps(install(a.output,a.node,a.npm_cli,confirmed=a.confirm_download)))
 except (OSError,ValueError,subprocess.SubprocessError) as error:raise SystemExit('First-run setup failed: '+str(error))
if __name__=='__main__':main()
