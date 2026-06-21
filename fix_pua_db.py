import sqlite3, re

conn = sqlite3.connect('data/questions.db')
c = conn.cursor()

paired = [
    ('\uf0ee', '(', ')'),
    ('\uf0f6', '[', ']'),
    ('\uf0f4', '|', '|'),
    ('\uf0f7', '\u230a', '\u230b'),
    ('\uf0f8', '\u2308', '\u2309'),
]
single = {
    '\uf0e0': '',
    '\uf0e1': '',
    '\uf0e2': '',
    '\uf00a': "'",
    '\uf0e8': '\u23a7',
    '\uf0e9': '\u23ab',
    '\uf0ea': '\u23aa',
    '\uf0e3': '\u23a7',
    '\uf0e4': '\u222a',
    '\uf0b1': '\u2211',
    '\uf0dc': '\u0305',
    '\uf0fb': '\u23df',
    '\uf0fc': '\u23df',
    '\uf0fd': '\u23df',
}
pua_re = re.compile('[\ue000-\uf8ff]')

def repair(text):
    if not text:
        return text
    for ch, op, cl in paired:
        pat = re.escape(ch) + r'\s+' + re.escape(ch)
        text = re.sub(pat, op + cl, text)
        text = text.replace(ch, op)
    for ch, rep in single.items():
        text = text.replace(ch, rep)
    return text

# Scan and fix
count = 0
fields = ['question_text', 'option_a', 'option_b', 'option_c', 'option_d']
all_rows = c.execute('SELECT id, question_text, option_a, option_b, option_c, option_d FROM questions').fetchall()

for row in all_rows:
    qid = row[0]
    needs_fix = False
    updates = {}
    for i, f in enumerate(fields):
        val = row[i + 1] or ''
        if val and pua_re.search(val):
            needs_fix = True
            updates[f] = repair(val)
    if needs_fix:
        set_clause = ', '.join(f'{f} = ?' for f in updates)
        values = list(updates.values()) + [qid]
        c.execute(f'UPDATE questions SET {set_clause} WHERE id = ?', values)
        count += 1

conn.commit()

remaining = 0
for row in c.execute('SELECT question_text FROM questions').fetchall():
    if row[0] and pua_re.search(row[0]):
        remaining += 1

print(f'Fixed: {count} questions')
print(f'Remaining PUA: {remaining}')
conn.close()
