"""Revision-bound changes to the existing procedure and shortcut files."""
import fcntl, hashlib, json, os, time, uuid
import memory_transactions as tx


def _path(directory, kind):
    if kind not in ('skills', 'workflows'): raise ValueError('Unsupported workflow store.')
    return os.path.join(directory, kind + '.json')


def _load(path):
    value = json.loads(tx._read(path))
    if not isinstance(value, dict) or any(not isinstance(k,str) for k in value): raise ValueError('Unsupported workflow store.')
    return value


def manage(directory, action, identifier='', revision='', value=None, backup_id='', confirmed=False, validate=None, supported=None):
    if confirmed is not True: raise ValueError('Explicit confirmation required.')
    lock_path=os.path.join(directory,'workflows.lock'); backups=os.path.join(directory,'memory-workflow-backups')
    if os.path.islink(lock_path) or os.path.islink(backups): raise ValueError('Symlinked workflow lock or backup folder.')
    with open(lock_path,'a') as lock:
        os.fchmod(lock.fileno(),0o600);fcntl.flock(lock,fcntl.LOCK_EX)
        if action == 'restore':
            if not isinstance(backup_id,str) or len(backup_id)!=32 or any(c not in '0123456789abcdef' for c in backup_id): raise ValueError('Invalid backup ID.')
            record=json.loads(tx._read(os.path.join(backups,backup_id+'.json'),16_001_000))
            if record.get('kind')!='workflow': raise ValueError('Invalid workflow backup.')
            path=_path(directory,record.get('store'));current=tx._read(path)
            if hashlib.sha256(current).hexdigest()!=record.get('after'): raise ValueError('Workflow store changed; restore cancelled.')
            restored=bytes.fromhex(record['before']);prior=json.loads(restored)
            if not isinstance(prior,dict): raise ValueError('Invalid workflow backup.')
            tx._write(path,restored);return {'status':'restored'}
        if action not in ('edit','delete') or not isinstance(identifier,str) or ':' not in identifier: raise ValueError('Unsupported workflow action.')
        kind,key=identifier.split(':',1);path=_path(directory,kind);before=tx._read(path);rows=_load(path)
        if kind=='skills' and (supported is None or not supported(rows)): raise ValueError('Unknown shortcut fields; no changes made.')
        if kind=='workflows' and any(not isinstance(v,str) for v in rows.values()): raise ValueError('Unknown procedure fields; no changes made.')
        if key not in rows: raise ValueError('Workflow not found.')
        old=rows[key]
        if not revision or tx.digest({'key':key,'record':old})!=revision: raise ValueError('Workflow changed since display.')
        if action=='delete': del rows[key]
        elif kind=='workflows':
            if not isinstance(value,str) or not value.strip() or len(value)>800: raise ValueError('Enter a procedure of at most 800 characters.')
            rows[key]=value.strip()
        else:
            if not isinstance(value,str) or len(value)>6000: raise ValueError('Invalid shortcut steps.')
            commands=[line.strip() for line in value.splitlines() if line.strip()]
            if not commands or validate is None or not validate(key,commands): raise ValueError('Shortcut steps are unsupported or unsafe.')
            entry=dict(old); previous=entry.get('evidence',{}); previous=previous if isinstance(previous,dict) else {}
            history=list(previous.get('corrections',[]));history.append({'previous_hash':tx.digest(old.get('cmds',[]))[:16],'at':time.time(),'reason':'owner edited steps'})
            entry['cmds']=commands
            entry['evidence']={**previous,'version':1,'source':'owner','confirmed':False,'successes':0,'confidence':0.0,'updated':time.time(),'corrections':history}
            rows[key]=entry
        after=json.dumps(rows,ensure_ascii=False,indent=2).encode('utf-8')
        os.makedirs(backups,mode=0o700,exist_ok=True);token=uuid.uuid4().hex
        record={'kind':'workflow','store':kind,'before':before.hex(),'after':hashlib.sha256(after).hexdigest(),'created':time.time()}
        tx._write(os.path.join(backups,token+'.json'),json.dumps(record).encode());tx._write(path,after)
        return {'status':'deleted' if action=='delete' else 'saved','backup':token}


def latest_recoverable(directory):
    backups=os.path.join(directory,'memory-workflow-backups')
    if os.path.islink(backups): return ''
    try:names=os.listdir(backups)
    except OSError:return ''
    found=[]
    for name in names:
        if len(name)!=37 or not name.endswith('.json') or any(c not in '0123456789abcdef' for c in name[:-5]):continue
        try:
            record=json.loads(tx._read(os.path.join(backups,name),16_001_000));path=_path(directory,record['store'])
            if record.get('kind')=='workflow' and hashlib.sha256(tx._read(path)).hexdigest()==record.get('after') and type(record.get('created')) in (int,float):found.append((record['created'],name[:-5]))
        except (OSError,ValueError,TypeError,KeyError,AttributeError):continue
    return max(found)[1] if found else ''
