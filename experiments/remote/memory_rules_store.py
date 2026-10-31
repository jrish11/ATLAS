"""Backward-compatible rule records. Migration only occurs on an explicit write."""
import re
import uuid

HEADER = '<!-- atticus-rule-ids:v1 -->\n'
LINE = re.compile(r'^- (.+) <!-- atticus-rule-id:([0-9a-f]{32}) -->\n$')


def parse(data):
    text = data.decode('utf-8')
    versioned = text.startswith(HEADER)
    lines = text[len(HEADER):].splitlines(keepends=True) if versioned else text.splitlines(keepends=True)
    result = []
    for line in lines:
        if versioned:
            match = LINE.fullmatch(line)
            if not match or not match[1].strip() or uuid.UUID(hex=match[2]).version != 4:
                raise ValueError('Unsupported rule format; no changes made.')
            result.append({'id': match[2], 'text': match[1]})
        else:
            if not line.startswith('- ') or not line.endswith('\n') or not line[2:-1].strip():
                raise ValueError('Unsupported rule format; no changes made.')
            result.append({'id': None, 'text': line[2:-1]})
    ids = [r['id'] for r in result if r['id']]
    if len(ids) != len(set(ids)): raise ValueError('Duplicate rule ID; no changes made.')
    return result


def migrate(rows):
    return [{'id': row['id'] or uuid.uuid4().hex, 'text': row['text']} for row in rows]


def encode(rows):
    ids = [row['id'] for row in rows]
    if len(ids) != len(set(ids)): raise ValueError('Duplicate rule ID; no changes made.')
    for row in rows:
        if not isinstance(row['text'], str) or not row['text'].strip() or '\n' in row['text'] or '\r' in row['text']:
            raise ValueError('Invalid rule.')
        try: identifier = uuid.UUID(hex=row['id'])
        except (ValueError, TypeError, AttributeError): raise ValueError('Invalid rule ID.')
        if identifier.version != 4 or identifier.hex != row['id']: raise ValueError('Invalid rule ID.')
    return (HEADER + ''.join('- ' + row['text'] + ' <!-- atticus-rule-id:' + row['id'] + ' -->\n' for row in rows)).encode('utf-8')
