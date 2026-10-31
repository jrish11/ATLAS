#!/usr/bin/env python3
"""Verify pinned public npm archives and collect exact-commit upstream license texts.

No package code or lifecycle script is executed. Network access is limited to
registry.npmjs.org and raw.githubusercontent.com; downloads remain local.
"""
import argparse,base64,hashlib,io,json,os,re,tarfile,urllib.parse,urllib.request
from pathlib import Path

MISSING={
 '@aws-sdk/credential-provider-http','@aws-sdk/credential-provider-login','@aws-sdk/nested-clients',
 '@earendil-works/pi-agent-core','@earendil-works/pi-ai','@earendil-works/pi-codemode',
 '@earendil-works/pi-coding-agent','@earendil-works/pi-mcp','@earendil-works/pi-telemetry','@earendil-works/pi-tui',
 'data-uri-to-buffer','proxy-agent-negotiate','standardwebhooks'}
MAX_ARCHIVE=40*1024*1024

def get(url,limit):
 u=urllib.parse.urlparse(url)
 if u.scheme!='https' or u.hostname not in ('registry.npmjs.org','raw.githubusercontent.com','api.github.com') or u.username or u.password:raise ValueError('Unapproved download origin')
 req=urllib.request.Request(url,headers={'User-Agent':'Atticus-release-provenance/1'})
 with urllib.request.urlopen(req,timeout=15) as response:
  if urllib.parse.urlparse(response.geturl()).hostname!=u.hostname:raise ValueError('Cross-origin redirect rejected')
  data=response.read(limit+1)
 if len(data)>limit:raise ValueError('Download exceeds bounded size')
 return data

def put(path,data):
 if path.exists():
  if path.read_bytes()!=data:raise ValueError('Existing staged file differs; refusing overwrite')
  return
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())

def repository(meta):
 repo=meta.get('repository');value=repo.get('url','') if isinstance(repo,dict) else repo if isinstance(repo,str) else ''
 match=re.fullmatch(r'(?:(?:git\+)?https://|git://)github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?',value)
 return match.groups() if match else None

def source_commit(meta,repo,version,tar_sha512):
 head=meta.get('gitHead')
 if isinstance(head,str) and re.fullmatch(r'[0-9a-f]{40}',head):return head,'npm gitHead'
 dist=meta.get('dist') or {};attest=dist.get('attestations') or {};url=attest.get('url')
 if isinstance(url,str):
  statements=json.loads(get(url,2*1024*1024)).get('attestations',[])
  for entry in statements:
   try:
    payload=json.loads(base64.b64decode(entry['bundle']['dsseEnvelope']['payload'],validate=True))
    if payload.get('predicateType')!='https://slsa.dev/provenance/v1':continue
    if not any(x.get('digest',{}).get('sha512')==tar_sha512 for x in payload.get('subject',[]) if isinstance(x,dict)):continue
    build=payload['predicate']['buildDefinition'];workflow=build['externalParameters']['workflow']
    if workflow.get('repository')!='https://github.com/'+repo[0]+'/'+repo[1]:continue
    for dependency in build.get('resolvedDependencies',[]):
     uri=dependency.get('uri','');commit=(dependency.get('digest') or {}).get('gitCommit')
     if uri.startswith('git+https://github.com/'+repo[0]+'/'+repo[1]+'@') and isinstance(commit,str) and re.fullmatch(r'[0-9a-f]{40}',commit):
      return commit,'npm provenance statement; signature not yet independently verified'
   except (KeyError,TypeError,ValueError):continue
 # Official exact-version tag, accepted only after package identity below matches.
 url='https://api.github.com/repos/'+repo[0]+'/'+repo[1]+'/git/ref/tags/v'+version
 try:obj=json.loads(get(url,1024*1024)).get('object',{})
 except urllib.error.HTTPError as e:
  if e.code==404:return None,None
  raise
 for _ in range(3):
  kind,sha=obj.get('type'),obj.get('sha')
  if not isinstance(sha,str) or not re.fullmatch(r'[0-9a-f]{40}',sha):return None,None
  if kind=='commit':return sha,'official exact-version tag'
  if kind!='tag':return None,None
  obj=json.loads(get('https://api.github.com/repos/'+repo[0]+'/'+repo[1]+'/git/tags/'+sha,1024*1024)).get('object',{})
 return None,None

def verify_source_identity(meta,repo,commit,name,version):
 repoinfo=meta.get('repository');directory=repoinfo.get('directory','') if isinstance(repoinfo,dict) else ''
 if not directory and name=='standardwebhooks':directory='libraries/javascript'
 if directory and (not isinstance(directory,str) or not re.fullmatch(r'[A-Za-z0-9_./-]+',directory) or '..' in directory.split('/')):raise ValueError('Unsafe repository subdirectory')
 url='https://raw.githubusercontent.com/'+repo[0]+'/'+repo[1]+'/'+commit+'/'+(directory+'/' if directory else '')+'package.json'
 try:package=json.loads(get(url,2*1024*1024))
 except urllib.error.HTTPError as e:
  if e.code==404:raise ValueError('Exact-commit source package manifest not found')
  raise
 if package.get('name')!=name or package.get('version')!=version:raise ValueError('Exact-commit source package identity does not match')
 return url

def verify(name,lock,root,installed):
 version,expected,tarurl=lock['version'],lock['integrity'],lock['resolved']
 if not re.fullmatch(r'[A-Za-z0-9@/_.-]+',name) or not re.fullmatch(r'[A-Za-z0-9.+_-]+',version):raise ValueError('Invalid package identity')
 if not isinstance(expected,str) or not expected.startswith('sha512-'):raise ValueError('Missing SHA-512 registry integrity')
 metaurl='https://registry.npmjs.org/'+urllib.parse.quote(name,safe='@')+'/'+urllib.parse.quote(version,safe='')
 meta=json.loads(get(metaurl,2*1024*1024))
 if meta.get('name')!=name or meta.get('version')!=version or (meta.get('dist') or {}).get('integrity')!=expected:raise ValueError('Registry metadata disagrees with lockfile')
 if (meta.get('dist') or {}).get('tarball')!=tarurl:raise ValueError('Registry tarball URL disagrees with lockfile')
 tar=get(tarurl,MAX_ARCHIVE);actual='sha512-'+base64.b64encode(hashlib.sha512(tar).digest()).decode()
 if actual!=expected:raise ValueError('Tarball SHA-512 integrity mismatch')
 with tarfile.open(fileobj=io.BytesIO(tar),mode='r:gz') as archive:
  members=archive.getmembers()
  if sum(m.size for m in members if m.isfile()) > 500*1024*1024 or any(m.size > 100*1024*1024 for m in members if m.isfile()):raise ValueError('Unpacked archive exceeds bounded size')
  manifest=archive.extractfile('package/package.json')
  if manifest is None:raise ValueError('Missing package manifest')
  package=json.load(manifest)
  if package.get('name')!=name or package.get('version')!=version:raise ValueError('Tarball identity mismatch')
  key=hashlib.sha256((name+'@'+version).encode()).hexdigest()
  put(root/'tarballs'/(key+'.tgz'),tar)
  checked=0
  for member in members:
   if not member.isfile():continue
   path=Path(member.name)
   if not path.parts or path.parts[0]!='package' or '..' in path.parts or path.is_absolute():raise ValueError('Unsafe tarball path')
   relative=Path(*path.parts[1:]);destination=installed/name/relative
   if (not destination.is_file() or destination.is_symlink() or
       os.path.commonpath((str(installed.resolve()),str(destination.resolve())))!=str(installed.resolve())):raise ValueError('Installed package differs from registry archive')
   content=archive.extractfile(member)
   if content is None:raise ValueError('Cannot read archive entry')
   h=hashlib.sha256()
   for block in iter(lambda:content.read(1024*1024),b''):h.update(block)
   local=hashlib.sha256()
   with open(destination,'rb') as f:
    for block in iter(lambda:f.read(1024*1024),b''):local.update(block)
   if h.digest()!=local.digest():raise ValueError('Installed package differs from registry archive')
   checked+=1
  license_files=[m for m in members if m.isfile() and re.fullmatch(r'package/(?:LICEN[CS]E|COPYING)(?:\.[A-Za-z0-9_-]+)?',m.name,re.I)]
  notice=archive.extractfile(license_files[0]).read(512*1024+1) if license_files else None
  notice_source=tarurl+'#'+license_files[0].name if license_files else None
 repo=repository(meta);head=meta.get('gitHead');evidence=None;identity_url=None
 if not notice:
  if not repo:raise ValueError('No root license in tarball and no verifiable GitHub repository')
  head,evidence=source_commit(meta,repo,version,hashlib.sha512(tar).hexdigest())
  if not head:raise ValueError('No root license in tarball and no exact source commit or tag')
  identity_url=verify_source_identity(meta,repo,head,name,version)
  for basename in ('LICENSE','LICENSE.md','LICENSE.txt','COPYING'):
   url='https://raw.githubusercontent.com/'+repo[0]+'/'+repo[1]+'/'+head+'/'+basename
   try:notice=get(url,512*1024);notice_source=url;break
   except urllib.error.HTTPError as error:
    if error.code!=404:raise
  if not notice and name == 'data-uri-to-buffer':
   url='https://raw.githubusercontent.com/'+repo[0]+'/'+repo[1]+'/'+head+'/README.md'
   text=get(url,512*1024).decode('utf-8')
   match=re.search(r'(?ms)^License\n-+\n\n(.*?)(?=\n\n\[|\Z)',text)
   if match and 'Permission is hereby granted' in match.group(1) and 'THE SOFTWARE IS PROVIDED' in match.group(1):
    notice=match.group(1).encode();notice_source=url+'#license'
  if not notice:raise ValueError('Exact-commit upstream license text not found')
 if len(notice)<100 or len(notice)>512*1024:raise ValueError('License text is empty or unexpectedly sized')
 key=hashlib.sha256((name+'@'+version).encode()).hexdigest();put(root/'tarballs'/(key+'.tgz'),tar);put(root/'notices'/(key+'.txt'),notice)
 return {'name':name,'version':version,'registry_metadata':metaurl,'tarball':tarurl,'integrity':expected,'tarball_sha256':hashlib.sha256(tar).hexdigest(),'license_identifier':meta.get('license'),'installed_files_verified':checked,'git_commit':head if isinstance(head,str) and re.fullmatch(r'[0-9a-f]{40}',head) else None,'source_evidence':evidence,'source_identity_url':identity_url,'license_source':notice_source,'license_sha256':hashlib.sha256(notice).hexdigest(),'notice_file':key+'.txt'}

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--lockfile',required=True,type=Path);parser.add_argument('--staging',required=True,type=Path);parser.add_argument('--installed',required=True,type=Path);args=parser.parse_args()
 lock=json.loads(args.lockfile.read_text());records=lock.get('packages',{});selected={}
 for path,row in records.items():
  if path.startswith('node_modules/'):
   name=path.split('node_modules/')[-1]
   if name in MISSING:
    if name in selected:raise SystemExit('Duplicate target package in lockfile: '+name)
    selected[name]=row
 if set(selected)!=MISSING:raise SystemExit('Lockfile does not match the 13 requested packages')
 args.staging.mkdir(parents=True,exist_ok=True,mode=0o700)
 for name in ('tarballs','notices'):(args.staging/name).mkdir(mode=0o700,exist_ok=True)
 results=[];errors=[]
 for name in sorted(selected):
  try:
   results.append(verify(name,selected[name],args.staging,args.installed));print(name+': verified',flush=True)
  except Exception as error:
   key=hashlib.sha256((name+'@'+selected[name]['version']).encode()).hexdigest();archive=args.staging/'tarballs'/(key+'.tgz')
   errors.append({'name':name,'error':type(error).__name__+': '+str(error)[:250], 'archive_integrity_verified':archive.is_file()});print(name+': NOT VERIFIED ('+type(error).__name__+')',flush=True)
   if isinstance(error,(PermissionError,urllib.error.URLError)) and not isinstance(error,urllib.error.HTTPError):break
 report={'format':1,'packages':results,'errors':errors,'all_verified':len(results)==len(MISSING)}
 put(args.staging/'provenance.json',(json.dumps(report,indent=2,sort_keys=True)+'\n').encode())
 if not report['all_verified']:raise SystemExit(1)
if __name__=='__main__':main()
