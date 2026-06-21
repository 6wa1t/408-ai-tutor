import sqlite3, re, os
conn = sqlite3.connect('data/questions.db')
c = conn.cursor()

pua_re = re.compile('[\ue000-\uf8ff]')

subjects = c.execute('SELECT subject, COUNT(*) FROM questions GROUP BY subject').fetchall()
for s, cnt in subjects:
    sample = c.execute('SELECT question_text FROM questions WHERE subject=? LIMIT 999', (s,)).fetchall()
    pua = sum(1 for row in sample if row[0] and pua_re.search(row[0]))
    img = c.execute("SELECT COUNT(*) FROM questions WHERE subject=? AND image_path IS NOT NULL AND image_path != ''", (s,)).fetchone()[0]
    print(f'  {s}: {cnt} 题, PUA={pua}, 有图={img}')

# Verify 机组 images
img_rows = c.execute("SELECT image_path FROM questions WHERE subject='计算机组成原理' AND image_path IS NOT NULL AND image_path != ''").fetchall()
on_disk = 0
missing = 0
for row in img_rows:
    paths = row[0].split(',')
    for p in paths:
        p = p.strip()
        full = os.path.join('D:\\project code\\408-ai-tutor\\images', p)
        if os.path.exists(full):
            on_disk += 1
        else:
            missing += 1
print(f'\n机组图: DB记录={len(img_rows)} 条, 磁盘存在={on_disk}, 缺失={missing}')

total = c.execute('SELECT COUNT(*) FROM questions').fetchone()[0]
all_texts = c.execute('SELECT question_text FROM questions').fetchall()
pua_total = sum(1 for row in all_texts if row[0] and pua_re.search(row[0]))
print(f'\n总: {total} 题, PUA残留总计: {pua_total}')
conn.close()
