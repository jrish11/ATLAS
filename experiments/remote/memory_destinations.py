"""Owner-initiated, local destination edits with single-record rollback.

Uses the existing destination registry and its lock; backups stay in the profile.
"""
import fcntl, hashlib, json, os, tempfile, time, uuid
import personal_commands as destinations

FIELDS={'label','url','aliases','browser','source','confirmed','confidence','updated','scope','corrections'}
def digest(rows):
    return hashlib.sha256(json.dumps(rows,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def write(path, obj):
    folder=os.path.dirname(path); os.makedirs(folder,mode=0o700,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix='.memory-',dir=folder)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            os.fchmod(f.fileno(),0o600);json.dump(obj,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)
def manage(directory, action, label='', url='', aliases=None, backup_id='', confirmed=False, revision=''):
    if confirmed is not True: raise ValueError('Explicit confirmation required.')
    os.makedirs(directory,mode=0o700,exist_ok=True)
    path=os.path.join(directory,'destinations.json'); backups=os.path.join(directory,'memory-backups')
    with open(os.path.join(directory,'destinations.lock'),'a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        try:
            with open(path,encoding='utf-8') as f: rows=json.load(f)
        except FileNotFoundError: rows=[]
        if not isinstance(rows,list):raise ValueError('Invalid destination registry.')
        if action=='restore':
            if not isinstance(backup_id,str) or len(backup_id)!=32 or any(c not in '0123456789abcdef' for c in backup_id):raise ValueError('Invalid backup ID.')
            with open(os.path.join(backups,backup_id+'.json'),encoding='utf-8') as f: old=json.load(f)
            if old.get('kind')!='destination' or digest(rows)!=old.get('after_digest'):raise ValueError('Registry changed since backup; restore cancelled.')
            before=old['before']; previous=old.get('after')
            if previous is not None: rows.remove(previous)
            rows.append(before); write(path,rows)
            return {'status':'restored'}
        matches=[r for r in rows if isinstance(r,dict) and r.get('label')==label]
        if len(matches)!=1:raise ValueError('Destination not found or ambiguous.')
        before=matches[0]
        allowed = FIELDS | ({'type','path','file_revision'} if before.get('type') == 'document' and action == 'delete' else set())
        if set(before)-allowed or (before.get('type') == 'document' and action != 'delete'):raise ValueError('Unknown destination fields; no changes made.')
        if before.get('confirmed') is not True:raise ValueError('Only owner-confirmed destinations can be edited here.')
        if not revision or revision!=digest(before):raise ValueError('Destination changed since it was displayed; refresh and try again.')
        if action=='delete': after=None
        elif action=='edit':
            if not destinations.validate_url(url):raise ValueError('Use an HTTPS address without credentials, query or fragment.')
            if not isinstance(aliases,list) or not all(isinstance(x,str) for x in aliases):raise ValueError('Invalid aliases.')
            names=list(dict.fromkeys(destinations.normalize(x) for x in [label]+aliases if destinations.normalize(x)))
            if any(set(names)&set(r.get('aliases',[])) for r in rows if r is not before):raise ValueError('An alias belongs to another destination.')
            after=dict(before);history=list(before.get('corrections',[])) if isinstance(before.get('corrections',[]),list) else []
            history.append({'id':destinations.new_correction_id(rows),'url':before.get('url'),'aliases':before.get('aliases'),'browser':before.get('browser'),'corrected_at':time.time(),'source':'owner','confirmed':True})
            after.update(url=url,aliases=names,source='owner',confirmed=True,confidence=1.0,scope='device',updated=time.time(),corrections=history[-20:])
        else:raise ValueError('Unsupported action.')
        new=[r for r in rows if r is not before]
        if after is not None:new.append(after)
        identifier=uuid.uuid4().hex
        write(os.path.join(backups,identifier+'.json'),{'kind':'destination','before':before,'after':after,'after_digest':digest(new),'created':time.time()})
        write(path,new)
        return {'status':'saved' if after else 'deleted','backup':identifier}

def latest_recoverable(directory):
    """Expose only an opaque ID, never backup contents; concurrent changes disable restore."""
    folder=os.path.join(directory,'memory-backups')
    try:
        rows=destinations.read(directory); candidates=[]
        for name in os.listdir(folder):
            if len(name)!=37 or not name.endswith('.json') or any(c not in '0123456789abcdef' for c in name[:-5]):continue
            try:
                with open(os.path.join(folder,name),encoding='utf-8') as f: record=json.load(f)
                if record.get('kind')=='destination' and record.get('after_digest')==digest(rows):
                    candidates.append((record.get('created',0),name[:-5]))
            except (OSError,ValueError,TypeError):continue
        return max(candidates)[1] if candidates else ''
    except OSError:return ''
