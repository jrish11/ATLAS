"""Revision-bound management of destination correction history."""
import fcntl, hashlib, json, os, time, uuid
import memory_destinations
import personal_commands


def digest(value): return memory_destinations.digest(value)


def legacy_id(label, item):
    return 'legacy:' + digest([label, item])


def _load(path):
    if os.path.islink(path): raise ValueError('Symlinked store is unsupported.')
    if os.path.getsize(path) > 8_000_000: raise ValueError('Destination registry is too large.')
    with open(path, encoding='utf-8') as f: rows = json.load(f)
    if not isinstance(rows, list): raise ValueError('Invalid destination registry.')
    seen = set()
    for row in rows:
        if not isinstance(row, dict): raise ValueError('Unsupported destination record.')
        corrections = row.get('corrections', [])
        if not isinstance(corrections, list): raise ValueError('Unsupported correction history.')
        for item in corrections:
            if not isinstance(item, dict): raise ValueError('Unsupported correction record.')
            if 'id' in item:
                try: identifier = uuid.UUID(hex=item['id'])
                except (ValueError, TypeError, AttributeError): raise ValueError('Invalid correction ID.')
                if identifier.version != 4 or identifier.hex != item['id'] or item['id'] in seen: raise ValueError('Duplicate or invalid correction ID.')
                seen.add(item['id'])
    return rows


def _items(rows):
    for row in rows:
        for item in row.get('corrections', []):
            yield row, item


def manage(directory, action, identifier='', revision='', value=None, backup_id='', confirmed=False):
    if confirmed is not True: raise ValueError('Explicit confirmation required.')
    path = os.path.join(directory, 'destinations.json')
    lock_path = os.path.join(directory, 'destinations.lock')
    backups = os.path.join(directory, 'memory-correction-backups')
    if os.path.islink(lock_path) or os.path.islink(backups): raise ValueError('Symlinked lock or backup folder.')
    with open(lock_path, 'a') as lock:
        os.fchmod(lock.fileno(), 0o600); fcntl.flock(lock, fcntl.LOCK_EX)
        rows = _load(path)
        if action == 'restore':
            if not isinstance(backup_id,str) or len(backup_id)!=32 or any(c not in '0123456789abcdef' for c in backup_id): raise ValueError('Invalid backup ID.')
            backup_path=os.path.join(backups,backup_id+'.json')
            if os.path.islink(backup_path): raise ValueError('Symlinked backup is unsupported.')
            with open(backup_path, encoding='utf-8') as f: backup=json.load(f)
            if backup.get('kind')!='correction' or digest(rows)!=backup.get('after'): raise ValueError('Registry changed; restore cancelled.')
            memory_destinations.write(path,backup['before']); return {'status':'restored'}
        if action not in ('edit','delete'): raise ValueError('Unsupported action.')
        matches=[(parent,item) for parent,item in _items(rows) if (('correction:'+item['id']) if item.get('id') else legacy_id(parent.get('label'),item))==identifier]
        if len(matches)!=1: raise ValueError('Correction not found or ambiguous.')
        parent,item=matches[0]
        if parent.get('confirmed') is not True: raise ValueError('Only confirmed destinations can be managed.')
        if not revision or digest(item)!=revision: raise ValueError('Correction changed since display.')
        if action=='edit' and not personal_commands.validate_url(value): raise ValueError('Use an HTTPS address without credentials, query or fragment.')
        used = {old['id'] for _,old in _items(rows) if 'id' in old}
        for _,old in _items(rows):
            if 'id' not in old:
                candidate = uuid.uuid4().hex
                if candidate in used: raise ValueError('Correction ID collision; no changes made.')
                old['id'] = candidate; used.add(candidate)
        # IDs must survive undo, including the first migration.
        before=json.loads(json.dumps(rows,ensure_ascii=False))
        if action=='delete': parent['corrections'].remove(item)
        else: item['url']=value
        os.makedirs(backups,mode=0o700,exist_ok=True)
        token=uuid.uuid4().hex
        memory_destinations.write(os.path.join(backups,token+'.json'),{'kind':'correction','before':before,'after':digest(rows),'created':time.time()})
        memory_destinations.write(path,rows)
        return {'status':'deleted' if action=='delete' else 'saved','backup':token}


def latest_recoverable(directory):
    backups=os.path.join(directory,'memory-correction-backups')
    if os.path.islink(backups): return ''
    try: rows=_load(os.path.join(directory,'destinations.json')); names=os.listdir(backups)
    except (OSError,ValueError,TypeError): return ''
    found=[]
    for name in names:
        if len(name)!=37 or not name.endswith('.json') or any(c not in '0123456789abcdef' for c in name[:-5]): continue
        path=os.path.join(backups,name)
        if os.path.islink(path): continue
        try:
            with open(path,encoding='utf-8') as f: record=json.load(f)
            if record.get('kind')=='correction' and record.get('after')==digest(rows) and type(record.get('created')) in (float,int): found.append((record['created'],name[:-5]))
        except (OSError,ValueError,TypeError,AttributeError): continue
    return max(found)[1] if found else ''
