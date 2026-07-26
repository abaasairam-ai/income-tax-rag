"""Chunk the Income-tax Act, 2025 and Income-tax Rules, 2026 for a RAG.

Strategy (structure first, size second):
  1. Split at SECTION / RULE boundaries -- the natural unit of legal meaning.
     "What does section 22 say" should return section 22, whole.
  2. Only sub-split a section that is too long, and only at its own
     sub-clause boundaries "(1) (2) (3)" -- never mid-sentence.
  3. Leave short sections alone. A 40-word section is a complete chunk.
  4. Stamp EVERY chunk with a citation header (Act/Rules, chapter, number,
     heading, part). This makes the number searchable and the citation
     available to the model at answer time.

No overlap between chunks: sections are self-contained, and overlapping would
duplicate law -- which is worse than useless in a tax assistant.
"""
import json
import re
import sys

sys.path.insert(0, '.')
from detect import detect_sections

MAX_WORDS = 600          # sub-split anything longer than this
FULL_TABLE_MAX = 10000   # skip emitting a whole-table chunk beyond this

# Split points, tried in order of preference. Legal text nests like this:
#   (1) sub-section  ->  (a) clause  ->  (i) sub-clause
# Some sections (e.g. s.536 "Repeal and savings", s.393 TDS tables) are long
# tables with no sub-numbering at all, so the last resort is a line budget --
# which still never cuts mid-line, only between lines.
LEVELS = [
    re.compile(r'^\((\d+)\)'),           # (1) (2) (3)
    re.compile(r'^\(([a-z]{1,3})\)'),    # (a) (b) ... and (i) (ii) roman
    re.compile(r'^\(([A-Z]{1,3})\)'),    # (A) (B)
    re.compile(r'^(\d{1,3})\.'),         # numbered table rows
]


def _units_by(pattern, lines):
    starts = [i for i, ln in enumerate(lines) if pattern.match(ln.strip())]
    if not starts:
        return None
    if starts[0] != 0:
        starts = [0] + starts
    return [lines[s:(starts[k + 1] if k + 1 < len(starts) else len(lines))]
            for k, s in enumerate(starts)]


def _pack(units, max_words):
    """Greedily pack units into parts under max_words."""
    parts, cur, cur_w = [], [], 0
    for u in units:
        w = len(' '.join(u).split())
        if cur and cur_w + w > max_words:
            parts.append(cur)
            cur, cur_w = list(u), w
        else:
            cur.extend(u)
            cur_w += w
    if cur:
        parts.append(cur)
    return parts


def split_long(body_lines, max_words=MAX_WORDS, _depth=0):
    """Recursively split a long section, preferring the highest structural level."""
    if len(' '.join(body_lines).split()) <= max_words:
        return [body_lines]

    for pat in LEVELS[_depth:]:
        units = _units_by(pat, body_lines)
        if units and len(units) > 1:
            parts = _pack(units, max_words)
            # recurse into any part still too big, using deeper levels
            out = []
            for p in parts:
                if len(' '.join(p).split()) > max_words and _depth + 1 < len(LEVELS):
                    out.extend(split_long(p, max_words, _depth + 1))
                else:
                    out.append(p)
            return out

    # No structure left: pack by line budget (never cuts mid-line).
    return _pack([[l] for l in body_lines], max_words)


TABLE_RE = re.compile(r'^TABLE\s*$')
COL_LETTER = re.compile(r'^[A-H]$')


def find_table(body):
    """Locate a TABLE and the end of its column-header block.

    Returns (table_start, header_end) indices into `body`, or None.
    The header block looks like:
        TABLE / FOR PAYMENTS TO RESIDENT / Sl. No. / Nature ... / A / B / C / D
    Rows follow. Without the header, a retrieved row is meaningless -- you
    cannot tell which column a figure belongs to.
    """
    for i, ln in enumerate(body):
        if TABLE_RE.match(ln.strip()):
            last = i
            for j in range(i + 1, min(i + 35, len(body))):
                if COL_LETTER.match(body[j].strip()):
                    last = j
            return (i, last)
    return None


def build_chunks(text_path, max_number, source_label, unit_word, body_end=None):
    """unit_word: 'section' or 'rule'."""
    lines = open(text_path, encoding='utf-8').read().split('\n')
    if body_end:
        lines = lines[:body_end]
    secs = detect_sections(lines, max_number)

    chunks = []
    for idx, s in enumerate(secs):
        if s['line'] is None:
            continue
        start = s['line']
        # body runs to the line before the next detected section
        nxt = next((t['line'] for t in secs[idx + 1:] if t['line'] is not None), len(lines))
        body = [l for l in lines[start:nxt] if l.strip()]
        if not body:
            continue

        # --- citation header, shared by every chunk of this section ---
        label = f"{unit_word.capitalize()} {s['number']}"
        base = f"{source_label} | {label}"
        if s['heading']:
            base += f" - {s['heading']}"
        if s['chapter']:
            base += f" | {s['chapter']}"

        tbl = find_table(body)
        parts = split_long(body)

        # Where does each part begin? parts partition body in order.
        offsets, run = [], 0
        for p in parts:
            offsets.append(run)
            run += len(p)

        for pi, (part, off) in enumerate(zip(parts, offsets), start=1):
            lines_out = list(part)
            repeated = False
            # If this part starts AFTER the table header, re-attach the header
            # so its rows keep their column meaning.
            #
            # BUT only when the part has enough content of its own. Measured on
            # the real Act, a small fragment ended up 80% header / 20% content --
            # which means its EMBEDDING describes the header, not the content,
            # so it matched any table-ish query and crowded out real answers.
            # Repeat the header only if the body clearly outweighs it.
            if tbl and off > tbl[1]:
                hdr = body[tbl[0]:tbl[1] + 1]
                if len(' '.join(part).split()) >= 2 * len(' '.join(hdr).split()):
                    lines_out = hdr + ['(table header repeated)'] + lines_out
                    repeated = True

            head = base + (f" | part {pi} of {len(parts)}" if len(parts) > 1 else "")
            text = head + '\n' + '\n'.join(lines_out)

            # Skip chunks with no substantive content -- fragments like "(7) (8)"
            # where a numbered list split across a boundary. They carry no
            # meaning, but they still occupy a retrieval slot.
            if len(re.findall(r'[A-Za-z]{3,}', '\n'.join(part))) < 5:
                continue

            chunks.append({
                'id': f"{unit_word}-{s['number']}-p{pi}",
                'source': source_label, 'unit': unit_word, 'number': s['number'],
                'heading': s['heading'], 'chapter': s['chapter'],
                'part': pi, 'of_parts': len(parts),
                'table_header_repeated': repeated,
                'is_full_table': False,
                'words': len(text.split()), 'text': text,
            })

        # --- ALSO emit the whole table as one chunk -----------------------
        # Useful when a question needs to compare rows ("which payments have a
        # 10% rate?"). NOTE: this chunk is far longer than an embedding model's
        # input limit, so its VECTOR only reflects the opening portion. Keep it
        # for reading/context, not as your main retrieval target.
        # Capture runs from the TABLE marker to the end of the section, so if a
        # section continues past its table the chunk includes that tail. Skip
        # absurdly large ones (s.536's repeal schedule is 30k+ words and is not
        # a table anyone would retrieve whole).
        if tbl and len(' '.join(body[tbl[0]:]).split()) <= FULL_TABLE_MAX:
            whole = body[tbl[0]:]
            text = (base + " | FULL TABLE" + '\n' + '\n'.join(whole))
            chunks.append({
                'id': f"{unit_word}-{s['number']}-table",
                'source': source_label, 'unit': unit_word, 'number': s['number'],
                'heading': s['heading'], 'chapter': s['chapter'],
                'part': 0, 'of_parts': len(parts),
                'table_header_repeated': False,
                'is_full_table': True,
                'words': len(text.split()), 'text': text,
            })
    return chunks


if __name__ == '__main__':
    out_dir = sys.argv[1]

    act = build_chunks('/tmp/act_clean.txt', 536,
                       'Income-tax Act, 2025 (as amended by Finance Act, 2026)',
                       'section')
    rules = build_chunks('/tmp/rules_body.txt', 333,
                         'Income-tax Rules, 2026 [G.S.R. 198(E) dated 20-3-2026]',
                         'rule')

    for name, data in (('act-chunks.jsonl', act), ('rules-chunks.jsonl', rules)):
        with open(f'{out_dir}/{name}', 'w', encoding='utf-8') as f:
            for c in data:
                f.write(json.dumps(c, ensure_ascii=False) + '\n')
        ws = sorted(c['words'] for c in data)
        print(f"{name}: {len(data)} chunks | "
              f"min {ws[0]}w  median {ws[len(ws)//2]}w  max {ws[-1]}w")
