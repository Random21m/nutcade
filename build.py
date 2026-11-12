#!/usr/bin/env python3
"""Builds public/index.html from src/: the files named in src/template.html (/*@@name@@*/ markers) are inlined,
so the app stays one self-contained page.

  python3 build.py           write public/index.html
  python3 build.py --check   exit 1 if public/index.html isn't exactly what src/ builds (run by CI)
"""
import os, re, sys
ROOT = os.path.dirname(os.path.abspath(__file__))
SRC, OUT = os.path.join(ROOT, 'src'), os.path.join(ROOT, 'public', 'index.html')

def build():
    page = open(os.path.join(SRC, 'template.html'), encoding='utf-8').read()
    for _ in range(3):   # app.js itself includes app_r4.js and app_r4_actions.js
        page = re.sub(r'/\*@@([\w.]+)@@\*/', lambda m: open(os.path.join(SRC, m.group(1)), encoding='utf-8').read(), page)
    return page

if __name__ == '__main__':
    page = build()
    if '--check' in sys.argv:
        same = os.path.exists(OUT) and open(OUT, encoding='utf-8').read() == page
        print('public/index.html matches src/' if same else 'public/index.html is out of date: run python3 build.py and commit it')
        sys.exit(0 if same else 1)
    open(OUT, 'w', encoding='utf-8').write(page)
    print('wrote', OUT, len(page.encode('utf-8')), 'bytes')
