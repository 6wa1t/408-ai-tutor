import requests, sys

base = 'http://127.0.0.1:8000'
for t in ['choice', 'other']:
    r = requests.get(base + '/api/questions/random', params={'count': 2, 'subject': '计算机组成原理', 'question_type': t}, timeout=5)
    print('type=%s: status=%d' % (t, r.status_code))
    if r.status_code == 200:
        data = r.json()
        qs = data.get('questions', [])
        print('  questions=%d' % len(qs))
        for q in qs[:1]:
            print('  Q%d: %s' % (q['id'], q['question_text'][:60].replace('\n', ' ')))
    else:
        print('  error: %s' % r.text[:100])
