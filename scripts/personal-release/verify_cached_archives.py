#!/usr/bin/env python3
"""Offline comparison of pinned registry archives with the installed package trees."""
import argparse,base64,hashlib,json,os,tarfile
from pathlib import Path
from provenance import MISSING

def sha(path,algorithm='sha256'):
 h=hashlib.new(algorithm)
 with open(path,'rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.digest()

def verify(name,row,archive,installed):
 expected=row['integrity'];actual='sha512-'+base64.b64encode(sha(archive,'sha512')).decode()
 if actual!=expected:raise ValueError('Archive SHA-512 mismatch')
 root=(installed/name).resolve();tree=set();count=0
 with tarfile.open(archive,'r:gz') as tar:
  entries=tar.getmembers()
  if sum(x.size for x in entries if x.isfile())>500*1024*1024:raise ValueError('Archive too large')
  for entry in entries:
   if not entry.isfile():
    if entry.issym() or entry.islnk():raise ValueError('Archive link requires manual review')
    continue
   parts=Path(entry.name).parts
   if not parts or parts[0]!='package' or '..' in parts or Path(entry.name).is_absolute() or entry.size>100*1024*1024:raise ValueError('Unsafe archive path')
   rel=Path(*parts[1:]);target=root/rel
   if not target.is_file() or target.is_symlink() or os.path.commonpath((str(root),str(target.resolve())))!=str(root):raise ValueError('Missing or unsafe installed file')
   h=hashlib.sha256();stream=tar.extractfile(entry)
   for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
   if sha(target)!=h.digest():raise ValueError('Installed file hash mismatch')
   tree.add(rel.as_posix());count+=1
  actual_tree=set()
  for base,dirs,files in os.walk(root,followlinks=False):
   dirs[:]=[x for x in dirs if x!='node_modules']
   if any((Path(base)/x).is_symlink() for x in dirs):raise ValueError('Unexpected installed symlink')
   for filename in files:actual_tree.add((Path(base)/filename).relative_to(root).as_posix())
  if tree!=actual_tree:raise ValueError('Unexpected installed file')
 return {'name':name,'version':row['version'],'registry_integrity':expected,'archive_sha256':sha(archive).hex(),'installed_files_verified':count}

def main():
 p=argparse.ArgumentParser();p.add_argument('--lockfile',type=Path,required=True);p.add_argument('--installed',type=Path,required=True);p.add_argument('--archives',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 lock=json.loads(a.lockfile.read_text())['packages'];rows=[]
 for name in sorted(MISSING):
  row=lock['node_modules/'+name];key=hashlib.sha256((name+'@'+row['version']).encode()).hexdigest()
  rows.append(verify(name,row,a.archives/(key+'.tgz'),a.installed))
 data=(json.dumps({'format':1,'packages':rows},sort_keys=True,indent=2)+'\n').encode();fd=os.open(a.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
 print(json.dumps({'verified_packages':len(rows),'verified_files':sum(x['installed_files_verified'] for x in rows)}))
if __name__=='__main__':main()
