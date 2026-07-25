"""Section detector for the Income-tax Act, 2025 / Rules, 2026.

Why this is fiddly (worth knowing before trusting any chunker):
  * Some sections have no space after the number:  "443.9[***]", "427.(1)"
  * One has a space BEFORE the period:             "94 . (1)"
  * Slab TABLES contain rows like "3. More than 1000000." which look identical
    to a section start.
  * The end of the file has FOOTNOTES numbered 1..N which also look identical.

So we can't trust the pattern alone. Three constraints together:
  1. the number must continue the sequence (1,2,3,... no jumps)
  2. it must appear before the end of the main body
  3. preferably the previous non-blank line is a HEADING (title text ending in
     a period, not numbered) -- that's what distinguishes a real section from
     a table row.
"""
import re

NUM = re.compile(r'^(\d{1,3})\s*\.')
CHAPTER = re.compile(r'^CHAPTER\s+([IVXLC]+)\s*$')
WINDOW = 400   # max lines a section may sit after the previous one


AMEND = re.compile(r'^\d*[a-z]?\[+')   # amendment markers: "3[", "[", "10b["


def _norm(line):
    """Strip amendment markers, stray brackets and quotes for testing."""
    s = AMEND.sub('', line.strip())
    return s.rstrip(']').strip()


def clean_heading(line):
    s = _norm(line)
    return s.rstrip('.').strip()


def is_heading(line):
    """A section heading: short title text, not numbered, not a table row.

    Headings here may be wrapped in amendment markers ("3[Fee for default..."),
    bracketed and closed with ']', start with a quoted term ('"Transfer" and
    "revocable transfer" defined.'), and may or may not end in a period.
    """
    s = _norm(line)
    if not s or len(s) > 200:
        return False
    if s.isupper():          # CHAPTER titles are all-caps, not section headings
        return False
    first = s.lstrip('"“\'').strip()   # allow a leading quoted term
    if not first or not (first[0].isalpha() and first[0].isupper()):
        return False
    # A heading ends with '.' or a letter. Continuation/table lines end with
    # ';' or ',' -- e.g. "Eight kilometres;" inside a slab table.
    return s.endswith('.') or s[-1].isalpha()


def prev_nonblank(lines, i):
    j = i - 1
    while j >= 0 and not lines[j].strip():
        j -= 1
    return (lines[j], j) if j >= 0 else ('', -1)


def heading_for(lines, i):
    """Heading immediately above line i, or None. Handles wrapped headings."""
    prev, pj = prev_nonblank(lines, i)
    if not prev.strip():
        return None
    if is_heading(prev):
        return clean_heading(prev)
    # Heading may WRAP across two lines; the tail starts lowercase.
    tail = prev.strip()
    if tail[:1].islower():
        above, _ = prev_nonblank(lines, pj)
        if is_heading(above):
            return clean_heading(above + ' ' + tail)
    return None


def detect_sections(lines, max_section):
    """Return list of dicts: number, line index, heading, chapter."""
    # index all candidate lines by number
    cands = {}
    for i, ln in enumerate(lines):
        m = NUM.match(ln)
        if m:
            cands.setdefault(int(m.group(1)), []).append(i)

    found, cursor = [], 0
    for n in range(1, max_section + 1):
        options = [i for i in cands.get(n, []) if i > cursor]
        if not options:
            found.append(None)
            continue
        # Prefer a candidate preceded by a proper heading, but stay NEAR the
        # previous section -- otherwise a stray "26." inside a form far away
        # (heading "Yes") hijacks the sequence and derails everything after.
        near = [i for i in options if i - cursor <= WINDOW]
        best = next((i for i in near if heading_for(lines, i)), None)
        if best is None:
            best = next((i for i in options if heading_for(lines, i)), None)
        if best is None:
            best = near[0] if near else options[0]
        found.append(best)
        cursor = best

    # attach headings + chapters
    out = []
    for n, i in enumerate(found, start=1):
        if i is None:
            out.append({'number': n, 'line': None, 'heading': None, 'chapter': None})
            continue
        heading = heading_for(lines, i)
        # nearest CHAPTER above
        chap = None
        for j in range(i, -1, -1):
            m = CHAPTER.match(lines[j].strip())
            if m:
                title = ''
                for k in range(j + 1, min(j + 3, len(lines))):
                    if lines[k].strip():
                        title = lines[k].strip()
                        break
                chap = f"CHAPTER {m.group(1)} - {title}"
                break
        out.append({'number': n, 'line': i, 'heading': heading, 'chapter': chap})
    return out


if __name__ == '__main__':
    import sys
    path, maxn = sys.argv[1], int(sys.argv[2])
    lines = open(path, encoding='utf-8').read().split('\n')
    secs = detect_sections(lines, maxn)
    missing = [s['number'] for s in secs if s['line'] is None]
    noheading = [s['number'] for s in secs if s['line'] is not None and not s['heading']]
    print(f"detected {sum(1 for s in secs if s['line'] is not None)}/{maxn}")
    print(f"missing: {len(missing)} {missing[:15]}")
    print(f"no heading found: {len(noheading)} {noheading[:15]}")
    ls = [s['line'] for s in secs if s['line'] is not None]
    print("strictly increasing:", all(ls[i] < ls[i + 1] for i in range(len(ls) - 1)))
    for s in secs[:3] + secs[92:95] + secs[-2:]:
        if s['line'] is not None:
            print(f"  s{s['number']}: line {s['line']+1} | {s['heading']} | {s['chapter']}")
