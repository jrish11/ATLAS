"""Revision-bound local mutations for stores whose writers share a lock."""
import fcntl, hashlib, json, os, re, tempfile, time, uuid
import personal_commands
import memory_inspector
import memory_rules_store

SENSITIVE = re.compile(r"\b(ssn|social security|credit card|debit card|card number|cvv|password|passcode|pin|health|medical|money|income|salary|bank|routing)\b", re.I)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def _write(path, data):
    folder = os.path.dirname(path)
    fd, temporary = tempfile.mkstemp(prefix='.memory-', dir=folder)
    try:
        with os.fdopen(fd, 'wb') as f:
            os.fchmod(f.fileno(), 0o600)
            f.write(data); f.flush(); os.fsync(f.fileno())
        os.replace(temporary, path)
        fd = os.open(folder, os.O_RDONLY)
        try: os.fsync(fd)
        finally: os.close(fd)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def _read(path, limit=8_000_000):
    if os.path.islink(path): raise ValueError('Symlinked store is unsupported.')
    with open(path, 'rb') as f: data = f.read(limit + 1)
    if len(data) > limit: raise ValueError('Store too large.')
    return data


def _decode(category, data):
    if category == 'rules': return memory_rules_store.parse(data)
    obj = json.loads(data)
    if category == 'profile' and isinstance(obj, dict) and set(obj) == {'version', 'facts'} and obj['version'] == 2 and isinstance(obj['facts'], list): return obj
    if category == 'projects' and isinstance(obj, list): return obj
    raise ValueError('Unsupported store format.')


def _encode(category, obj):
    if category == 'rules': return memory_rules_store.encode(obj)
    return json.dumps(obj, ensure_ascii=False, indent=2).encode()


def manage(directory, category, action, identifier='', revision='', value=None, backup_id='', confirmed=False, excluded=()):
    if confirmed is not True: raise ValueError('Explicit confirmation required.')
    if not isinstance(excluded, (list, tuple)) or any(not isinstance(x, str) or not os.path.isabs(x) for x in excluded): raise ValueError('Invalid folder exclusions.')
    names = {'profile': ('me.json', 'me.json.lock'), 'rules': ('memory.md', 'memory.md.lock'), 'projects': ('projects.json', 'projects.lock')}
    if category not in names: raise ValueError('Unsupported category.')
    name, lock_name = names[category]
    path, lock_path = os.path.join(directory, name), os.path.join(directory, lock_name)
    backups = os.path.join(directory, 'memory-transaction-backups')
    if os.path.islink(lock_path) or os.path.islink(backups): raise ValueError('Symlinked lock or backup directory.')
    with open(lock_path, 'a') as lock:
        os.fchmod(lock.fileno(), 0o600); fcntl.flock(lock, fcntl.LOCK_EX)
        before = _read(path); current = _decode(category, before)
        if action == 'restore':
            if len(backup_id) != 32 or any(c not in '0123456789abcdef' for c in backup_id): raise ValueError('Invalid backup ID.')
            record = json.loads(_read(os.path.join(backups, backup_id + '.json'), 16_001_000))
            if record.get('category') != category or record.get('after') != hashlib.sha256(before).hexdigest(): raise ValueError('Store changed; restore cancelled.')
            restored = bytes.fromhex(record['before']); prior = _decode(category, restored)
            if category == 'projects' and any(not isinstance(row, dict) or not memory_inspector.in_scope(row.get('folder'), excluded) for row in current + prior): raise ValueError('Project restore includes an excluded or unscoped folder.')
            _write(path, restored)
            return {'status': 'restored'}
        if action not in ('edit', 'delete'): raise ValueError('Unsupported action.')
        rows = current['facts'] if category == 'profile' else current
        # The recovery copy contains the whole registry, so do not copy excluded projects.
        if category == 'projects' and excluded and any(not isinstance(row, dict) or not memory_inspector.in_scope(row.get('folder'), excluded) for row in rows):
            raise ValueError('Project registry contains an excluded or unscoped folder; no backup created.')
        key = lambda row: (('rule:' + row['id']) if row.get('id') else row.get('text')) if category == 'rules' and isinstance(row, dict) else row.get('id' if category == 'profile' else 'label') if isinstance(row, dict) else None
        found = [i for i, row in enumerate(rows) if key(row) == identifier]
        if len(found) != 1: raise ValueError('Record not found or ambiguous.')
        index = found[0]; old = rows[index]
        if not revision or revision != digest((old if old.get('id') else old['text']) if category == 'rules' else old): raise ValueError('Record changed since display.')
        if category == 'rules':
            rows[:] = memory_rules_store.migrate(rows)
            before = _encode(category, current)
            old = rows[index]
        if category == 'profile':
            if not isinstance(old, dict) or set(old) - {'id','category','kind','value','source','date','sensitive'} or old.get('sensitive') or SENSITIVE.search(str(old.get('kind', '')) + ' ' + str(old.get('value', ''))): raise ValueError('Unsupported or private profile record.')
            if action == 'edit':
                if not isinstance(value, str) or not value.strip() or len(value) > 300 or '\n' in value: raise ValueError('Invalid profile value.')
                value = ' '.join(value.split())
                if SENSITIVE.search(str(old.get('kind', '')) + ' ' + value): raise ValueError('Sensitive profile values cannot be saved here.')
                new = dict(old, value=value)
        elif category == 'projects':
            if not isinstance(old, dict) or set(old) - {'label','folder','aliases','confirmed','source','scope','updated'} or old.get('confirmed') is not True: raise ValueError('Unsupported project record.')
            if not memory_inspector.in_scope(old.get('folder'), excluded): raise ValueError('Project is excluded.')
            if action == 'edit':
                if not isinstance(value, dict) or set(value) != {'folder','aliases'} or not isinstance(value['folder'], str) or not os.path.isabs(value['folder']) or not os.path.isdir(value['folder']) or not isinstance(value['aliases'], list) or any(not isinstance(x, str) for x in value['aliases']): raise ValueError('Invalid project.')
                if not memory_inspector.in_scope(value['folder'], excluded): raise ValueError('Project folder is excluded.')
                names = list(dict.fromkeys(personal_commands.normalize(x) for x in [old['label']] + value['aliases'] if personal_commands.normalize(x)))
                if any(set(names) & set(r.get('aliases', [])) for i, r in enumerate(rows) if i != index and isinstance(r, dict)): raise ValueError('Alias conflict.')
                new = dict(old, folder=os.path.realpath(value['folder']), aliases=names, updated=time.time())
        elif action == 'edit':
            if not isinstance(value, str) or not value.strip() or '\n' in value or '\r' in value: raise ValueError('Invalid rule.')
            new = ' '.join(value.split())
            if any(i != index and r['text'].casefold() == new.casefold() for i, r in enumerate(rows)): raise ValueError('Duplicate rule.')
            new = dict(old, text=new)
        if action == 'delete': rows.pop(index)
        else: rows[index] = new
        after = _encode(category, current)
        os.makedirs(backups, mode=0o700, exist_ok=True)
        token = uuid.uuid4().hex
        record = {'version':1, 'category':category, 'before':before.hex(), 'after':hashlib.sha256(after).hexdigest(), 'created':time.time()}
        _write(os.path.join(backups, token + '.json'), json.dumps(record).encode())
        _write(path, after)
        return {'status':'deleted' if action == 'delete' else 'saved', 'backup':token}


def latest_recoverable(directory):
    """Return only identifiers whose complete store still matches the post-change bytes."""
    backups = os.path.join(directory, 'memory-transaction-backups')
    if os.path.islink(backups): return {}
    names = {'profile':'me.json', 'rules':'memory.md', 'projects':'projects.json'}
    result = {}
    try: entries = os.listdir(backups)
    except OSError: return result
    for name in entries:
        if len(name) != 37 or not name.endswith('.json') or any(c not in '0123456789abcdef' for c in name[:-5]): continue
        try:
            record = json.loads(_read(os.path.join(backups, name), 16_001_000))
            category = record.get('category')
            if category not in names: continue
            data = _read(os.path.join(directory, names[category]))
            if hashlib.sha256(data).hexdigest() != record.get('after'): continue
            created = record.get('created')
            if type(created) not in (int, float): continue
            if category not in result or created > result[category][0]: result[category] = (created, name[:-5])
        except (OSError, ValueError, TypeError, KeyError): continue
    return {category: pair[1] for category, pair in result.items()}
