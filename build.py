#!/usr/bin/env python3
"""Builds public/index.html from src/: the files named in src/template.html (/*@@name@@*/ markers) are inlined,
so the app stays one self-contained page.

  python3 build.py           write public/index.html
  python3 build.py --check   exit 1 if public/index.html isn't exactly what src/ builds (run by CI)
"""
import base64, hashlib, os, re, sys
ROOT = os.path.dirname(os.path.abspath(__file__))
SRC, OUT = os.path.join(ROOT, 'src'), os.path.join(ROOT, 'public', 'index.html')

def build():
    page = open(os.path.join(SRC, 'template.html'), encoding='utf-8').read()
    for _ in range(3):   # app.js itself includes app_r4.js and app_r4_actions.js
        page = re.sub(r'/\*@@([\w.]+)@@\*/', lambda m: open(os.path.join(SRC, m.group(1)), encoding='utf-8').read(), page)
    return add_csp(page)

# Content-Security-Policy (a <meta> tag: GitHub Pages sets no headers). Scripts run only if they are one of this page's own
# inline <script> blocks (matched by sha256, computed here from exactly what is built) or WebAssembly (the QR decoder).
# Connections stay open on purpose: mints and Nostr relays can be anywhere. Styles keep 'unsafe-inline' (the app writes style="" attributes).
# frame-ancestors cannot be set from a <meta> tag, so it is not listed.
def add_csp(page):
    hashes = sorted({"'sha256-" + base64.b64encode(hashlib.sha256(s.encode('utf-8')).digest()).decode() + "'"
                     for s in re.findall(r'<script>(.*?)</script>', page, re.S)})
    csp = "; ".join([
        "default-src 'none'",
        "script-src " + " ".join(hashes) + " 'wasm-unsafe-eval'",
        "style-src 'unsafe-inline'",
        "img-src 'self' data: blob:",
        "media-src 'self' data: blob:",
        "font-src data:",
        "connect-src https: wss: http: ws:",
        "worker-src 'self'",
        "manifest-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'none'"])
    return page.replace('<!--@@csp@@-->', '<meta http-equiv="Content-Security-Policy" content="' + csp + '">')

if __name__ == '__main__':
    page = build()
    if '--check' in sys.argv:
        same = os.path.exists(OUT) and open(OUT, encoding='utf-8').read() == page
        print('public/index.html matches src/' if same else 'public/index.html is out of date: run python3 build.py and commit it')
        sys.exit(0 if same else 1)
    open(OUT, 'w', encoding='utf-8').write(page)
    print('wrote', OUT, len(page.encode('utf-8')), 'bytes')
