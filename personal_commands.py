"""Confirmed, local-only destinations for Atticus's existing instant command path.

This registry deliberately contains no executable scripts or browser credentials.
"""
import fcntl
import json
import os
import re
import stat
import subprocess
import tempfile
import time
import uuid
from urllib.parse import urlsplit


def new_correction_id(rows):
    identifier = uuid.uuid4().hex
    for row in rows:
        history = row.get('corrections', []) if isinstance(row, dict) else []
        if isinstance(history, list) and any(isinstance(item, dict) and item.get('id') == identifier for item in history):
            raise ValueError('Correction ID collision; no changes made.')
    return identifier


def normalize(text):
    return ' '.join(re.findall(r"[a-z0-9]+", text.lower()))


def validate_url(url):
    try:
        parts = urlsplit(url)
        return bool(parts.scheme == 'https' and parts.hostname and not parts.username and not parts.password
                    and not parts.query and not parts.fragment and not any(c.isspace() for c in url))
    except (TypeError, ValueError, AttributeError):
        return False


def read(directory):
    try:
        with open(os.path.join(directory, 'destinations.json'), encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _read_for_mutation(directory):
    path = os.path.join(directory, 'destinations.json')
    if os.path.islink(path): raise ValueError('Symlinked destination store is unsupported.')
    try:
        if os.path.getsize(path) > 8_000_000: raise ValueError('Destination store is too large.')
        with open(path, encoding='utf-8') as f: rows = json.load(f)
    except FileNotFoundError: return []
    except (OSError, ValueError, TypeError) as e: raise ValueError('Destination store cannot be safely edited.') from e
    if not isinstance(rows, list): raise ValueError('Invalid destination store.')
    labels = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('label'), str) or not row['label'] or row['label'] in labels:
            raise ValueError('Unsupported or duplicate destination record.')
        labels.add(row['label'])
        aliases = row.get('aliases', [])
        if not isinstance(aliases, list) or any(not isinstance(x, str) for x in aliases): raise ValueError('Invalid destination aliases.')
        history = row.get('corrections', [])
        if not isinstance(history, list) or any(not isinstance(x, dict) for x in history): raise ValueError('Invalid correction history.')
    return rows


def save(directory, label, url, aliases, browser='Safari'):
    if not isinstance(label, str) or not isinstance(aliases, list) or any(not isinstance(x, str) for x in aliases): raise ValueError('Invalid destination name or aliases.')
    if not validate_url(url) or browser != 'Safari':
        raise ValueError('Use an HTTPS URL without credentials, query or fragment, and Safari.')
    names = list(dict.fromkeys(normalize(x) for x in [label] + aliases if normalize(x)))
    if not names:
        raise ValueError('A destination needs a name.')
    os.makedirs(directory, mode=0o700, exist_ok=True)
    if os.path.islink(os.path.join(directory, 'destinations.lock')): raise ValueError('Symlinked destination lock is unsupported.')
    with open(os.path.join(directory, 'destinations.lock'), 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        rows = _read_for_mutation(directory)
        if any(set(names) & set(r.get('aliases', [])) and r.get('label') != label for r in rows):
            raise ValueError('Alias already belongs to another destination.')
        previous = next((r for r in rows if r.get('label') == label), None)
        if previous and previous.get('type') == 'document': raise ValueError('Forget the document before replacing its destination.')
        history = list(previous.get('corrections', [])) if previous and isinstance(previous.get('corrections', []), list) else []
        if previous and (previous.get('url') != url or previous.get('aliases') != names or previous.get('browser') != browser):
            history.append({'id': new_correction_id(rows), 'url': previous.get('url'), 'aliases': previous.get('aliases'),
                            'browser': previous.get('browser'), 'corrected_at': time.time(),
                            'source': 'owner', 'confirmed': True})
        rows = [r for r in rows if r.get('label') != label]
        updated = dict(previous) if previous else {}
        updated.update({'label': label, 'url': url, 'aliases': names, 'browser': browser,
                        'source': 'owner', 'confirmed': True, 'confidence': 1.0,
                        'updated': time.time(), 'scope': 'device', 'corrections': history})
        rows.append(updated)
        fd, path = tempfile.mkstemp(prefix='.destinations-', dir=directory)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(rows, f, ensure_ascii=False, indent=2)
                f.flush(); os.fsync(f.fileno())
            os.replace(path, os.path.join(directory, 'destinations.json'))
        finally:
            if os.path.exists(path): os.unlink(path)


DOCUMENT_EXTENSIONS = {'.txt','.md','.pdf','.rtf','.docx','.xlsx','.pptx','.csv'}

def document_revision(path):
    if not isinstance(path,str) or not os.path.isabs(path) or os.path.realpath(path) != path or os.path.splitext(path)[1].lower() not in DOCUMENT_EXTENSIONS:
        raise ValueError('Choose a canonical supported document file.')
    try:
        initial=os.lstat(path)
        if not stat.S_ISREG(initial.st_mode): raise ValueError('Choose a regular document file.')
        fd=os.open(path,os.O_RDONLY | getattr(os,'O_NOFOLLOW',0) | getattr(os,'O_NONBLOCK',0))
        try:
            info=os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or (initial.st_dev,initial.st_ino)!=(info.st_dev,info.st_ino): raise ValueError('Choose a stable regular document file.')
            return {'device':info.st_dev,'inode':info.st_ino,'size':info.st_size,'mtime_ns':info.st_mtime_ns}
        finally: os.close(fd)
    except OSError as e: raise ValueError('The document is unavailable.') from e

def save_document(directory,label,path,aliases,confirmed=False):
    if confirmed is not True: raise ValueError('Explicit owner confirmation required.')
    if not isinstance(label,str) or not label.strip() or len(label)>120 or not isinstance(aliases,list) or any(not isinstance(x,str) for x in aliases): raise ValueError('Invalid document name or aliases.')
    revision=document_revision(path)
    names=list(dict.fromkeys(normalize(x) for x in [label]+aliases if normalize(x)))
    if not names: raise ValueError('A document needs a name.')
    os.makedirs(directory,mode=0o700,exist_ok=True)
    lockpath=os.path.join(directory,'destinations.lock')
    if os.path.islink(lockpath): raise ValueError('Symlinked destination lock is unsupported.')
    with open(lockpath,'a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX);rows=_read_for_mutation(directory)
        if any(set(names)&set(r.get('aliases',[])) or r.get('label')==label for r in rows): raise ValueError('Destination name or alias already exists.')
        if document_revision(path)!=revision: raise ValueError('Document changed during confirmation.')
        rows.append({'type':'document','label':label,'path':path,'file_revision':revision,'aliases':names,'confirmed':True,'source':'owner','scope':'device','updated':time.time()})
        fd,temp=tempfile.mkstemp(prefix='.destinations-',dir=directory)
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as f: json.dump(rows,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
            os.replace(temp,os.path.join(directory,'destinations.json'))
        finally:
            if os.path.exists(temp): os.unlink(temp)

def open_document(row, runner=subprocess.run):
    try:
        if not isinstance(row,dict) or row.get('type')!='document' or row.get('confirmed') is not True or not isinstance(row.get('label'),str) or not row['label'].strip(): return 'Invalid saved document; nothing was opened.'
        path=row.get('path');expected=row.get('file_revision')
        if not isinstance(expected,dict) or document_revision(path)!=expected: return 'The saved document changed or is unavailable; choose it again before opening.'
        result=runner(['/usr/bin/open','--',path],capture_output=True,text=True,timeout=5)
        return 'Requested opening '+row['label']+'; check that the document is ready.' if result.returncode == 0 else 'The document could not be opened.'
    except (OSError,ValueError,subprocess.TimeoutExpired): return 'The saved document changed or is unavailable; nothing was opened.'


def resolve(directory, text):
    match = re.fullmatch(r'(?:open(?: up)?|launch|pull up|bring up|focus on|switch to|go to)\s+(?:my\s+|the\s+)?(.+)', text.lower().strip())
    if not match:
        return None
    target = normalize(match.group(1))
    matches = [row for row in read(directory) if isinstance(row, dict) and row.get('confirmed') is True
               and isinstance(row.get('label'), str) and bool(row['label'].strip())
               and isinstance(row.get('aliases'), list) and target in row['aliases']
               and ((row.get('type') == 'document' and isinstance(row.get('path'),str)) or (validate_url(row.get('url', '')) and row.get('browser') == 'Safari'))]
    return matches[0] if len(matches) == 1 else {'ambiguous': True} if len(matches) > 1 else None


# Compare the complete URL, never a partial title or substring. The script only
# activates an already-open match; it never reads page content or credentials.
SAFARI_FIND = '''on run argv
set wanted to item 1 of argv
tell application "System Events" to set safariRunning to exists process "Safari"
if not safariRunning then return "absent"
tell application "Safari"
 set hits to {}
 repeat with w in windows
  repeat with t in tabs of w
   if (URL of t as text) is wanted then set end of hits to {w, t}
  end repeat
 end repeat
 if (count of hits) > 1 then return "ambiguous"
 if (count of hits) is 1 then
  set selectedWindow to item 1 of item 1 of hits
  set selectedTab to item 2 of item 1 of hits
  set current tab of selectedWindow to selectedTab
  set index of selectedWindow to 1
  activate
  return "switched"
 end if
end tell
return "absent"
end run'''



SAFARI_CURRENT = '''tell application "System Events" to set frontName to name of first application process whose frontmost is true
if frontName is not "Safari" then return "not-safari"
tell application "Safari"
 if (count windows) is 0 then return "no-window"
 return URL of current tab of front window as text
end tell'''


def remember_current(directory, label, runner=subprocess.run):
    """Save the front Safari tab only after the user's explicit remember command."""
    if not normalize(label): return 'Please name the destination you want me to remember.'
    try:
        result = runner(['/usr/bin/osascript', '-e', SAFARI_CURRENT], capture_output=True, text=True, timeout=5)
        if result.returncode != 0: return 'I could not read the Safari tab. Check Automation permission and try again.'
        url = result.stdout.strip()
        if url in ('not-safari', 'no-window'): return 'Bring the correct Safari page to the front and ask me again.'
        if not validate_url(url): return 'I cannot safely save this page address. It may contain private parameters or use an unsupported scheme.'
        save(directory, label, url, [])
        return 'Remembered ' + label + ' for this Mac.'
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return 'I could not save that destination. Check for a conflicting name or try again.'

def open_destination(row, runner=subprocess.run, authorize=lambda: True):
    if isinstance(row,dict) and row.get('type') == 'document': return open_document(row, runner)
    try:
        if not isinstance(row,dict) or not isinstance(row.get('label'),str) or not row['label'].strip() or not validate_url(row.get('url')) or row.get('browser', 'Safari') != 'Safari':
            return 'Invalid saved destination; nothing was opened.'
        url = row['url']
        wanted = url + '/' if urlsplit(url).path == '' else url
        if not authorize(): return 'Authorization expired or the request was cancelled; nothing was opened.'
        found = runner(['/usr/bin/osascript', '-e', SAFARI_FIND, wanted], capture_output=True, text=True, timeout=5)
        if found.returncode != 0:
            return 'I could not check Safari tabs. Check Automation permission and try again.'
        result = found.stdout.strip()
        if result == 'ambiguous':
            return 'More than one matching Safari tab is open. Please choose the right one.'
        if result == 'switched':
            return 'Requested switching to ' + row['label'] + ' in Safari; check the active tab.'
        if result != 'absent':
            return 'I could not verify Safari tabs; nothing was opened.'
        if not authorize(): return 'Authorization expired or the request was cancelled; nothing was opened.'
        opened = runner(['/usr/bin/open', '-a', 'Safari', row['url']], capture_output=True, text=True, timeout=5)
        return ('Requested ' + row['label'] + ' in Safari; check that the page loaded.' if opened.returncode == 0
                else 'Safari could not open ' + row['label'] + '.')
    except (OSError, subprocess.TimeoutExpired):
        return 'I could not check or open Safari. Try again.'


def remove(directory, label):
    os.makedirs(directory, mode=0o700, exist_ok=True)
    if os.path.islink(os.path.join(directory, 'destinations.lock')): raise ValueError('Symlinked destination lock is unsupported.')
    with open(os.path.join(directory, 'destinations.lock'), 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        rows = _read_for_mutation(directory)
        kept = [row for row in rows if row.get('label') != label]
        if len(rows) == len(kept): return False
        fd, path = tempfile.mkstemp(prefix='.destinations-', dir=directory)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(kept, f, ensure_ascii=False, indent=2)
                f.flush(); os.fsync(f.fileno())
            os.replace(path, os.path.join(directory, 'destinations.json'))
        finally:
            if os.path.exists(path): os.unlink(path)
        return True



def save_project(directory, label, folder, aliases):
    """Owner-confirmed project paths; never infer a path from a model response."""
    if not os.path.isabs(folder) or not os.path.isdir(folder): raise ValueError('Choose an existing absolute project folder.')
    names = list(dict.fromkeys(normalize(x) for x in [label] + aliases if normalize(x)))
    if not names: raise ValueError('A project needs a name.')
    os.makedirs(directory, mode=0o700, exist_ok=True)
    file = os.path.join(directory, 'projects.json')
    with open(os.path.join(directory, 'projects.lock'), 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            with open(file) as source: rows = json.load(source)
            if not isinstance(rows, list): raise ValueError('Project registry is invalid.')
        except FileNotFoundError: rows = []
        if any(set(names) & set(r.get('aliases', [])) and r.get('label') != label for r in rows):
            raise ValueError('Alias already belongs to another project.')
        rows = [r for r in rows if r.get('label') != label]
        rows.append({'label':label, 'folder':os.path.realpath(folder), 'aliases':names,
                     'confirmed':True, 'source':'owner', 'scope':'device', 'updated':time.time()})
        fd, temp = tempfile.mkstemp(prefix='.projects-', dir=directory)
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(rows, f, indent=2); f.flush(); os.fsync(f.fileno())
            os.replace(temp, file)
        finally:
            if os.path.exists(temp): os.unlink(temp)


def resolve_project(directory, request):
    try:
        with open(os.path.join(directory, 'projects.json')) as f: rows = json.load(f)
        if not isinstance(rows, list): return None
    except (OSError, ValueError): return None
    words = ' ' + normalize(request) + ' '
    hits = [row for row in rows if isinstance(row, dict) and row.get('confirmed') is True and
            isinstance(row.get('aliases'), list) and any(' ' + a + ' ' in words for a in row['aliases'] if isinstance(a, str) and a) and
            isinstance(row.get('folder'), str) and os.path.isabs(row['folder']) and os.path.isdir(row['folder'])]
    return hits[0] if len(hits) == 1 else {'ambiguous':True} if len(hits) > 1 else None


def project_list(directory):
    try:
        with open(os.path.join(directory, 'projects.json')) as f: rows = json.load(f)
        return rows if isinstance(rows, list) else []
    except (OSError, ValueError): return []


def delete_project(directory, label):
    os.makedirs(directory, mode=0o700, exist_ok=True)
    path = os.path.join(directory, 'projects.json')
    with open(os.path.join(directory, 'projects.lock'), 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            with open(path) as source: rows = json.load(source)
        except FileNotFoundError: return False
        if not isinstance(rows, list): raise ValueError('Project registry is invalid.')
        keep = [row for row in rows if row.get('label') != label]
        if len(keep) == len(rows): return False
        fd, temp = tempfile.mkstemp(prefix='.projects-', dir=directory)
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(keep, f, indent=2); f.flush(); os.fsync(f.fileno())
            os.replace(temp, path)
        finally:
            if os.path.exists(temp): os.unlink(temp)
        return True


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Manage explicitly confirmed local Atticus destinations.')
    parser.add_argument('--directory', required=True, help='Atticus profile directory')
    commands = parser.add_subparsers(dest='action', required=True)
    add = commands.add_parser('add')
    add.add_argument('label'); add.add_argument('url'); add.add_argument('--alias', action='append', default=[])
    commands.add_parser('list')
    delete = commands.add_parser('delete'); delete.add_argument('label')
    project = commands.add_parser('add-project')
    project.add_argument('label'); project.add_argument('folder'); project.add_argument('--alias', action='append', default=[])
    commands.add_parser('list-projects')
    project_delete = commands.add_parser('delete-project'); project_delete.add_argument('label')
    args = parser.parse_args()
    if args.action == 'add':
        save(args.directory, args.label, args.url, args.alias)
        print('Saved owner-confirmed destination.')
    elif args.action == 'add-project':
        save_project(args.directory, args.label, args.folder, args.alias)
        print('Saved owner-confirmed project.')
    elif args.action == 'list-projects':
        print(json.dumps(project_list(args.directory), indent=2, ensure_ascii=False))
    elif args.action == 'delete-project':
        print('Deleted.' if delete_project(args.directory, args.label) else 'No matching project.')
    elif args.action == 'delete':
        print('Deleted.' if remove(args.directory, args.label) else 'No matching destination.')
    else:
        print(json.dumps(read(args.directory), indent=2, ensure_ascii=False))
