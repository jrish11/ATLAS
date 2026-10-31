"""Immutable, local journal entries for verified task records in an existing vault.

No shared note is overwritten; daily summaries are generated from entries on read.
"""
import datetime
import os
from pathlib import Path
import re
import tempfile


class JournalError(Exception): pass


def _safe_line(value):
    return re.sub(r'\s+', ' ', str(value)).strip().replace('<', '&lt;').replace('>', '&gt;')[:400]


def _vault(vault):
    root = Path(vault).resolve(strict=True)
    if not root.is_dir() or not (root / '.obsidian').is_dir(): raise JournalError('Choose an existing Obsidian vault.')
    return root


def _folder(parent, name, create=False):
    path = parent / name
    if path.is_symlink(): raise JournalError('The journal path may not be a symlink.')
    if create: path.mkdir(mode=0o700, exist_ok=True)
    if path.exists() and not path.is_dir(): raise JournalError('The journal path is not a folder.')
    return path


def journal_completed(vault, record, before_publish=None):
    root = _vault(vault)
    if record.get('status') != 'done' or record.get('verified') is not True:
        raise JournalError('Only independently verified completed tasks can be journaled.')
    identifier = str(record.get('id', ''))
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', identifier): raise JournalError('Invalid task identifier.')
    try: day = datetime.datetime.fromtimestamp(float(record['ended'])).date().isoformat()
    except (KeyError, ValueError, OverflowError, TypeError, OSError) as e: raise JournalError('A real completion time is required.') from e
    title = _safe_line(record.get('title', ''))
    if not title: raise JournalError('A completed task needs a title.')
    folder = _folder(_folder(_folder(root, 'Atticus', True), 'Agent Activity', True), day, True)
    target = folder / (identifier + '.md')
    content = ('---\ntype: atticus-verified-activity\ndate: ' + day + '\n---\n\n'
               '# Verified activity\n\n- ' + title + '\n\n<!-- atticus-task:' + identifier + ' -->\n').encode('utf-8')
    fd, temp = tempfile.mkstemp(prefix='.atticus-entry-', dir=folder)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(content); f.flush(); os.fsync(f.fileno())
        if before_publish: before_publish(target)
        try:
            # Atomic create-if-absent. No shared note or existing entry is replaced.
            os.link(temp, target, follow_symlinks=False)
            return {'status':'written', 'path':str(target)}
        except FileExistsError:
            if target.is_symlink() or not target.is_file(): return {'status':'conflict'}
            return {'status':'duplicate' if target.read_bytes() == content else 'conflict', 'path':str(target)}
    finally:
        if os.path.exists(temp): os.unlink(temp)


def daily_summary(vault, day):
    root = _vault(vault)
    try: datetime.date.fromisoformat(day)
    except (TypeError, ValueError) as e: raise JournalError('Use a date in YYYY-MM-DD format.') from e
    folder = _folder(_folder(_folder(root, 'Atticus'), 'Agent Activity'), day)
    if not folder.is_dir(): return []
    lines = []
    for file in sorted(folder.glob('*.md')):
        if file.is_symlink() or not file.is_file() or file.stat().st_size > 8192: continue
        try: text = file.read_text(encoding='utf-8')
        except (OSError, UnicodeError): continue
        match = re.search(r'^- (.+)$', text, re.M)
        marker = re.search(r'<!-- atticus-task:([A-Za-z0-9_-]{1,80}) -->', text)
        if match and marker and file.stem == marker.group(1): lines.append({'id':marker.group(1), 'title':match.group(1)})
    return lines
