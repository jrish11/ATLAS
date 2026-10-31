"""Owner-confirmed, local-only import into the existing About You profile."""
import argparse
import fcntl
import hashlib
import json
import os
import re
import sys
import time
import uuid

import memory_transactions as tx

CATEGORIES = {'basics', 'school_work', 'preferences', 'notes'}
PRIVATE = re.compile(r'\b(password|passcode|secret|token|api.?key|credential|ssn|medical|health|diagnosis|salary|bank|credit.?card)\b', re.I)


def validate(seed):
    if not isinstance(seed, dict) or set(seed) != {'version', 'records'} or seed['version'] != 1 or not isinstance(seed['records'], list) or len(seed['records']) > 50:
        raise ValueError('Invalid profile file.')
    seen = set()
    for row in seed['records']:
        if not isinstance(row, dict) or set(row) != {'category', 'kind', 'value'} or row['category'] not in CATEGORIES:
            raise ValueError('Invalid record or category.')
        for key, limit in [('kind', 40), ('value', 300)]:
            value = row[key]
            if not isinstance(value, str) or not value.strip() or value != ' '.join(value.split()) or len(value) > limit or PRIVATE.search(value):
                raise ValueError('Invalid or private record.')
        key = (row['category'].casefold(), row['kind'].casefold())
        if key in seen: raise ValueError('Duplicate record kind in import.')
        seen.add(key)
    return seed


def snapshot(directory, seed, expected=None, confirmed=False):
    validate(seed)
    if not os.path.isdir(directory) or os.path.islink(directory): raise ValueError('Profile directory unavailable.')
    path = os.path.join(directory, 'me.json'); lockpath = path + '.lock'
    if os.path.islink(lockpath): raise ValueError('Unsafe lock.')
    with open(lockpath, 'a') as lock:
        os.fchmod(lock.fileno(), 0o600); fcntl.flock(lock, fcntl.LOCK_EX)
        try: before = tx._read(path)
        except FileNotFoundError: before = b''
        current = tx._decode('profile', before) if before else {'version': 2, 'facts': []}
        rows = current['facts']
        allowed = {'id', 'category', 'kind', 'value', 'source', 'date', 'sensitive'}
        if any(not isinstance(f, dict) or set(f) - allowed or not all(isinstance(f.get(k), str) for k in ('id', 'category', 'kind', 'value', 'source', 'date')) for f in rows):
            raise ValueError('Unsupported profile records; no changes made.')
        token = hashlib.sha256(before + b'\0' + json.dumps(seed, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        proposed = []
        for row in seed['records']:
            conflict = any(f['category'].casefold() == row['category'].casefold() and f['kind'].casefold() == row['kind'].casefold() for f in rows)
            proposed.append(dict(row, status='skip-existing' if conflict else 'add'))
        if not confirmed: return {'revision': token, 'records': proposed}
        if expected != token: raise ValueError('Profile or import changed since preview; start again.')
        for row in proposed:
            if row['status'] == 'add':
                rows.append({'id': 'seed-' + uuid.uuid4().hex, 'category': row['category'], 'kind': row['kind'], 'value': row['value'], 'source': 'you', 'date': time.strftime('%Y-%m-%d')})
        count = sum(r['status'] == 'add' for r in proposed)
        if count: tx._write(path, tx._encode('profile', current))
        return {'added': count, 'skipped': len(proposed) - count}


def main():
    parser = argparse.ArgumentParser(description='Preview and optionally import a local ATLAS profile file.')
    parser.add_argument('file'); args = parser.parse_args()
    try:
        data = tx._read(args.file, 40000); seed = validate(json.loads(data))
        directory = os.path.expanduser('~/.config/atticus-personal-dev')
        preview = snapshot(directory, seed)
        print('Local profile preview (no provider call; existing kinds are kept):')
        for r in preview['records']: print(f"  {r['status']}: {r['category']} / {r['kind']}: {r['value']}")
        if input('Type IMPORT to add the listed new records, or press Return to cancel: ') != 'IMPORT':
            print('Cancelled; nothing changed.'); return
        result = snapshot(directory, seed, preview['revision'], confirmed=True)
        print(f"Imported {result['added']}; kept {result['skipped']} existing record(s).")
    except (OSError, ValueError, EOFError, json.JSONDecodeError) as error:
        print('Import stopped:', error, file=sys.stderr); sys.exit(1)

if __name__ == '__main__': main()
