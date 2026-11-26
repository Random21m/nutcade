"""src/lib.min.js is rebuildable: tools/build_lib.sh (tools/lib/: package.json, package-lock.json, entry.js, esbuild 0.28.2)
builds a bundle that is byte-for-byte the shipped src/lib.min.js. No browser, no test mint: needs node and npm and the npm registry.
Run: python3 tests/lib_build_check.py   (CI job lib-build)"""
import hashlib, os, subprocess, sys, tempfile
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sha = lambda b: hashlib.sha256(b).hexdigest()
shipped = open(os.path.join(ROOT, 'src', 'lib.min.js'), 'rb').read()
with tempfile.TemporaryDirectory(prefix='libbuild-') as d:
    out = os.path.join(d, 'lib.min.js')
    r = subprocess.run(['bash', os.path.join(ROOT, 'tools', 'build_lib.sh'), out], capture_output=True, text=True)
    if r.returncode:
        print('FAIL build: tools/build_lib.sh exited %d\n%s' % (r.returncode, r.stderr[-2000:])); sys.exit(1)
    built = open(out, 'rb').read()
ok = built == shipped
print(('PASS' if ok else 'FAIL') + ' rebuild: tools/build_lib.sh gives exactly src/lib.min.js (%d bytes, sha256 %s; built %d bytes, %s)'
      % (len(shipped), sha(shipped), len(built), sha(built)))
sys.exit(0 if ok else 1)
