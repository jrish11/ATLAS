#!/usr/bin/env python3
"""Compare a local arm64 Node binary with the official HTTPS release archive; never run it."""
import argparse,hashlib,io,json,os,re,tarfile,urllib.request
from pathlib import Path
MAX=100*1024*1024

def fetch(url,limit):
 req=urllib.request.Request(url,headers={'User-Agent':'Atticus-release-provenance/1'})
 with urllib.request.urlopen(req,timeout=30) as response:
  if not response.geturl().startswith('https://nodejs.org/'):raise ValueError('Unexpected download redirect')
  data=response.read(limit+1)
 if len(data)>limit:raise ValueError('Download too large')
 return data

def digest(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for data in iter(lambda:f.read(1024*1024),b''):h.update(data)
 return h.hexdigest()

def save(path,data):
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())

def main():
 p=argparse.ArgumentParser();p.add_argument('--version',required=True);p.add_argument('--binary',type=Path,required=True);p.add_argument('--staging',type=Path,required=True);a=p.parse_args()
 if not re.fullmatch(r'v\d+\.\d+\.\d+',a.version):raise SystemExit('Invalid Node version')
 name='node-'+a.version+'-darwin-arm64.tar.gz';base='https://nodejs.org/dist/'+a.version+'/'
 checks=fetch(base+'SHASUMS256.txt',4*1024*1024).decode('ascii');matches=[x.split()[0] for x in checks.splitlines() if len(x.split())==2 and x.split()[1]==name]
 if len(matches)!=1 or not re.fullmatch(r'[0-9a-f]{64}',matches[0]):raise SystemExit('Official checksum entry unavailable')
 archive=fetch(base+name,MAX)
 if hashlib.sha256(archive).hexdigest()!=matches[0]:raise SystemExit('Official archive checksum mismatch')
 prefix='node-'+a.version+'-darwin-arm64/'
 with tarfile.open(fileobj=io.BytesIO(archive),mode='r:gz') as t:
  item=t.getmember(prefix+'bin/node');license_item=t.getmember(prefix+'LICENSE')
  if not item.isfile() or item.size>200*1024*1024 or not license_item.isfile() or license_item.size>2*1024*1024:raise SystemExit('Invalid archive structure')
  h=hashlib.sha256();stream=t.extractfile(item)
  for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
  license_bytes=t.extractfile(license_item).read()
 local=digest(a.binary);official=h.hexdigest()
 a.staging.mkdir(parents=True,mode=0o700,exist_ok=True)
 report={'version':a.version,'architecture':'darwin-arm64','archive_url':base+name,'archive_sha256':matches[0],
         'checksums_url':base+'SHASUMS256.txt','signature_verified':False,'signature_note':'HTTPS checksum only; detached signature verification remains required',
         'official_node_sha256':official,'local_node_sha256':local,'local_matches_official':local==official,
         'license_sha256':hashlib.sha256(license_bytes).hexdigest()}
 save(a.staging/'Node-LICENSE.txt',license_bytes);save(a.staging/'node-provenance.json',(json.dumps(report,sort_keys=True,indent=2)+'\n').encode())
 print(json.dumps(report));
 if local!=official:raise SystemExit(1)
if __name__=='__main__':main()
