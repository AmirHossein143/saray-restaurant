"""Compile every ``*.po`` under this folder to ``*.mo`` without GNU gettext.

Usage (from the project folder)::

    python locale/compile_mo.py

``python manage.py compilemessages`` does the same when GNU gettext's
``msgfmt`` is installed; this script exists because it usually is not on
Windows. Supports msgctxt and plural forms (the subset of the PO format used
by the catalogs in this folder).
"""

import array
import ast
import re
import sys
from pathlib import Path

_KEYWORD = re.compile(r'^(msgctxt|msgid_plural|msgid|msgstr(?:\[(\d+)\])?)\s+(".*")\s*$')


def parse_po(text):
    """Return ``{key: translation}`` with gettext's encoding of context and plurals."""
    messages = {}
    entry, current = {}, None

    def flush():
        if 'msgid' in entry and not entry.get('fuzzy'):
            msgid = entry['msgid']
            if 'msgctxt' in entry:
                msgid = f'{entry["msgctxt"]}\x04{msgid}'
            if 'msgid_plural' in entry:
                key = f'{msgid}\x00{entry["msgid_plural"]}'
                forms = [entry['plurals'][i] for i in sorted(entry.get('plurals', {}))]
                value = '\x00'.join(forms)
            else:
                key, value = msgid, entry.get('msgstr', '')
            if value.replace('\x00', ''):
                messages[key] = value
        entry.clear()

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith('#'):
            if line.startswith('#,') and 'fuzzy' in line:
                if 'msgid' in entry:
                    flush()
                entry['fuzzy'] = True
            continue
        match = _KEYWORD.match(line)
        if match:
            keyword, index, literal = match.groups()
            if keyword in ('msgctxt', 'msgid') and 'msgid' in entry and current not in ('msgctxt',):
                flush()
            value = ast.literal_eval(literal)
            if index is not None:
                entry.setdefault('plurals', {})[int(index)] = value
                current = ('plural', int(index))
            else:
                entry[keyword] = value
                current = keyword
        elif line.startswith('"') and current is not None:
            value = ast.literal_eval(line)
            if isinstance(current, tuple):
                entry['plurals'][current[1]] += value
            else:
                entry[current] += value
        else:
            raise ValueError(f'Cannot parse line: {raw!r}')
    flush()
    return messages


def write_mo(messages, path):
    """Write a GNU .mo file (little-endian, no hash table)."""
    keys = sorted(messages)
    ids = b''
    strs = b''
    offsets = []
    for key in keys:
        k, v = key.encode('utf-8'), messages[key].encode('utf-8')
        offsets.append((len(ids), len(k), len(strs), len(v)))
        ids += k + b'\x00'
        strs += v + b'\x00'
    count = len(keys)
    keystart = 7 * 4 + 16 * count
    valuestart = keystart + len(ids)
    koffsets, voffsets = [], []
    for o1, l1, o2, l2 in offsets:
        koffsets += [l1, o1 + keystart]
        voffsets += [l2, o2 + valuestart]
    header = array.array('I', [0x950412DE, 0, count, 7 * 4, 7 * 4 + count * 8, 0, 0])
    body = array.array('I', koffsets + voffsets)
    if sys.byteorder != 'little':
        header.byteswap()
        body.byteswap()
    Path(path).write_bytes(header.tobytes() + body.tobytes() + ids + strs)


def main():
    root = Path(__file__).resolve().parent
    for po in sorted(root.rglob('*.po')):
        messages = parse_po(po.read_text(encoding='utf-8'))
        mo = po.with_suffix('.mo')
        write_mo(messages, mo)
        print(f'{po.relative_to(root)} -> {mo.name} ({len(messages) - ("" in messages)} messages)')


if __name__ == '__main__':
    main()
