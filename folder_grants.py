"""Local, explicit folder-scope records. Never bypasses OS or action approvals."""
import fcntl,json,os,stat,tempfile,time,uuid


def identity(path):
 if not isinstance(path,str) or not os.path.isabs(path) or os.path.realpath(path)!=path: raise ValueError('Choose an existing canonical folder.')
 try:
  fd=os.open(path,os.O_RDONLY|getattr(os,'O_DIRECTORY',0)|getattr(os,'O_NOFOLLOW',0))
  try:
   item=os.fstat(fd);current=os.stat(path,follow_symlinks=False)
   if not stat.S_ISDIR(item.st_mode) or os.path.realpath(path)!=path or (item.st_dev,item.st_ino)!=(current.st_dev,current.st_ino):raise ValueError('Folder changed.')
   return {'device':item.st_dev,'inode':item.st_ino}
  finally:os.close(fd)
 except OSError as e:raise ValueError('Folder unavailable or not accessible.') from e


def _read(path):
 try:
  fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
  with os.fdopen(fd,'rb') as f:data=f.read(1_000_001)
 except FileNotFoundError:return []
 except OSError as e:raise ValueError('Unsupported grant registry.') from e
 if len(data)>1_000_000:raise ValueError('Grant registry too large.')
 obj=json.loads(data)
 if not isinstance(obj,dict) or set(obj)!={'version','grants'} or obj['version']!=1 or not isinstance(obj['grants'],list):raise ValueError('Unsupported grant registry.')
 seen=set()
 for r in obj['grants']:
  if not isinstance(r,dict) or set(r)!={'id','path','access','identity','created'} or not isinstance(r['id'],str) or len(r['id'])!=32 or any(c not in '0123456789abcdef' for c in r['id']) or r['id'] in seen or not isinstance(r['path'],str) or r['access'] not in ('read','write') or not isinstance(r['identity'],dict) or set(r['identity'])!={'device','inode'} or any(type(r['identity'][k]) is not int for k in ('device','inode')) or type(r['created']) not in (int,float):raise ValueError('Unsupported grant record.')
  seen.add(r['id'])
 return obj['grants']


def _write(path,rows):
 fd,temp=tempfile.mkstemp(prefix='.folder-grants-',dir=os.path.dirname(path))
 try:
  with os.fdopen(fd,'w') as f:os.fchmod(f.fileno(),0o600);json.dump({'version':1,'grants':rows},f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
  os.replace(temp,path)
  fd=os.open(os.path.dirname(path),os.O_RDONLY)
  try:os.fsync(fd)
  finally:os.close(fd)
 finally:
  if os.path.exists(temp):os.unlink(temp)


def manage(directory,action,path='',access='',identifier='',expected=None,confirmed=False):
 registry=os.path.join(directory,'folder-grants.json');lockfile=os.path.join(directory,'folder-grants.lock')
 if os.path.islink(directory) or os.path.islink(lockfile):raise ValueError('Grant storage unavailable.')
 if action=='list' and not os.path.lexists(registry):return {'grants':[]}
 if action=='add' and confirmed is True:os.makedirs(directory,mode=0o700,exist_ok=True)
 if not os.path.isdir(directory):raise ValueError('Grant storage unavailable.')
 try: lockfd=os.open(lockfile,os.O_CREAT|os.O_RDWR|getattr(os,'O_NOFOLLOW',0),0o600)
 except OSError as e:raise ValueError('Grant lock unavailable.') from e
 with os.fdopen(lockfd,'r+') as lock:
  os.fchmod(lock.fileno(),0o600);fcntl.flock(lock,fcntl.LOCK_EX);rows=_read(registry)
  if action=='list':
   output=[]
   for row in rows:
    try:valid=identity(row['path'])==row['identity']
    except ValueError:valid=False
    output.append({**row,'available':valid})
   return {'grants':output}
  if confirmed is not True:raise ValueError('Owner confirmation required.')
  if action=='add':
   if access not in ('read','write'):raise ValueError('Invalid access.')
   current=identity(path)
   if not isinstance(expected,dict) or current!=expected:raise ValueError('Folder changed since review.')
   if any(x['path']==path and x['access']==access for x in rows):raise ValueError('That grant already exists.')
   rows.append({'id':uuid.uuid4().hex,'path':path,'access':access,'identity':current,'created':time.time()})
  elif action=='revoke':
   found=[x for x in rows if x['id']==identifier]
   if len(found)!=1 or expected!=found[0]['identity']:raise ValueError('Grant changed or disappeared.')
   rows.remove(found[0])
  else:raise ValueError('Unsupported grant action.')
  _write(registry,rows);return {'status':'saved' if action=='add' else 'revoked'}
